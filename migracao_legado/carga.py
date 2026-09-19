"""Carga do Gerenciador de Viagens (GV) para o módulo de viagens.

Lê o banco do GV só para leitura (`origem.abrir_origem`), tabela por tabela,
na ordem de dependência, e grava aqui dentro de uma transação — que é
desfeita no fim quando é simulação (o padrão). Cada linha trazida fica no
diário da carga (`Registro`: tabela e id na origem → modelo e id aqui), que é
o que torna a carga repetível sem duplicar e reversível:

- linha já trazida antes (está no diário): é atualizada;
- linha que já existe aqui (mesmo CPF, placa, nome, sigla...): é vinculada
  a ela — e os valores de antes ficam no diário, para desfazer;
- o resto é criado, com a marca de origem (`legado_origem`/`legado_pk`).

As linhas entram por `bulk_create`/`update`, sem `save()` nem sinais: nada
de numeração nova, prestação criada por sinal ou auditoria de formulário — o
que chega é o que existia lá. Arquivos (PDFs, anexos, assinados) são
conferidos e copiados para o `media/` daqui (`arquivos.py`); o que não passa
na conferência vai para a quarentena e o campo fica vazio.

Fora da carga: Google Drive, protocolos, trilha de auditoria do GV, gerações
de documento e anexos soltos de evento (não há onde guardar aqui). Contas de
usuário não são criadas: o autor de um registro é ligado ao usuário daqui com
o mesmo login ou e-mail, ou fica em branco.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Callable

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, DataError, models, transaction

ORIGEM = "gerenciador_viagens"
EXTENSOES = ["pdf", "docx", "xlsx", "png", "jpg", "jpeg"]


def normalizar(texto) -> str:
    texto = unicodedata.normalize("NFD", str(texto or "")).encode("ascii", "ignore").decode()
    return " ".join(texto.upper().split())


def digitos(texto) -> str:
    return "".join(c for c in str(texto or "") if c.isdigit())


def _json(valor):
    if isinstance(valor, Decimal):
        return str(valor)
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    return str(valor)


@dataclass
class Tabela:
    """Uma tabela do GV e o modelo daqui para onde ela vai."""

    nome: str
    modelo: str
    # coluna daqui → coluna do GV (FK é traduzida pelo modelo relacionado) ou
    # função (linha, carga) → valor final.
    colunas: dict = field(default_factory=dict)
    # Como achar o registro que já existe aqui: função (dados, linha, carga) → instância.
    existente: Callable | None = None
    # Ajuste final dos valores: função (dados, linha, carga).
    ajustar: Callable | None = None
    # Tabelas de muitos-para-muitos: (tabela do GV, campo daqui).
    m2m: tuple = ()
    # Só vincula ao que existe aqui; não cria nada.
    so_vincular: bool = False
    # Só as linhas da área escolhida (a coluna some aqui).
    por_area: bool = False


@dataclass
class Relatorio:
    criadas: int = 0
    vinculadas: int = 0
    atualizadas: int = 0
    reprovadas: list = field(default_factory=list)
    arquivos: dict = field(default_factory=lambda: defaultdict(int))
    vinculos_m2m: int = 0

    def como_dict(self):
        return {
            "criadas": self.criadas, "vinculadas": self.vinculadas, "atualizadas": self.atualizadas,
            "reprovadas": len(self.reprovadas), "motivos": self.reprovadas[:50],
            "arquivos": dict(self.arquivos), "vinculos_m2m": self.vinculos_m2m,
        }


# ---- Como reconhecer o que já existe aqui ---------------------------------


def _por_nome(campo="nome"):
    def achar(dados, linha, carga):
        modelo = carga.modelo_atual
        alvo = normalizar(dados.get(campo))
        if not alvo:
            return None
        return next((o for o in modelo.objects.all() if normalizar(getattr(o, campo)) == alvo), None)
    return achar


def _servidor(dados, linha, carga):
    from viagens_cadastros.models import Servidor

    cpf = digitos(dados.get("cpf"))
    if cpf:
        achado = Servidor.objects.filter(cpf=cpf).first()
        if achado:
            return achado
    return _por_nome()(dados, linha, carga)


def _viatura(dados, linha, carga):
    from viagens_cadastros.models import Viatura

    placa = normalizar(dados.get("placa")).replace("-", "").replace(" ", "")
    return Viatura.objects.filter(placa__iexact=placa).first() if placa else None


def _usuario(dados, linha, carga):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    achado = User.objects.filter(username__iexact=linha.get("username") or "").first()
    if not achado and linha.get("email"):
        achado = User.objects.filter(email__iexact=linha["email"]).first()
    return achado


def _estado(dados, linha, carga):
    from cadastros.models import Estado

    return Estado.objects.filter(sigla__iexact=linha.get("sigla") or "").first()


def _municipio(dados, linha, carga):
    from cadastros.models import Municipio

    if linha.get("codigo_ibge"):
        achado = Municipio.objects.filter(codigo_ibge=linha["codigo_ibge"]).first()
        if achado:
            return achado
    uf = (linha.get("uf") or "").upper()
    if not uf and linha.get("estado_id"):
        uf = carga.sigla_do_estado.get(linha["estado_id"], "")
    return carga.municipio_por_nome(linha.get("nome"), uf)


def _configuracao(dados, linha, carga):
    from viagens_cadastros.models import ConfiguracaoSistema

    return ConfiguracaoSistema.get_singleton()


def _unicos(dados, linha, carga):
    """Os campos únicos do próprio modelo (nome de catálogo, par configuração
    e tipo...): o registro daqui com os mesmos valores é o mesmo."""
    modelo = carga.modelo_atual
    conjuntos = [(f.attname,) for f in modelo._meta.concrete_fields if f.unique and not f.primary_key and not f.name.startswith("legado")]
    conjuntos += [tuple(modelo._meta.get_field(n).attname for n in grupo) for grupo in modelo._meta.unique_together]
    for regra in modelo._meta.constraints:
        if isinstance(regra, models.UniqueConstraint) and regra.condition is None and regra.fields:
            conjuntos.append(tuple(modelo._meta.get_field(n).attname for n in regra.fields))
    for conjunto in conjuntos:
        valores = {nome: dados.get(nome) for nome in conjunto}
        if any(v in (None, "") for v in valores.values()):
            continue
        achado = modelo._base_manager.filter(**valores).first()
        if achado:
            return achado
    return None


# ---- Ajustes de valores ----------------------------------------------------


def _ajustar_servidor(dados, linha, carga):
    dados["cpf"] = digitos(dados.get("cpf"))[:11]


def _ajustar_viatura(dados, linha, carga):
    dados["placa"] = normalizar(dados.get("placa")).replace("-", "").replace(" ", "")


def _ajustar_municipio(dados, linha, carga):
    # Completa o que falta aqui (capital, coordenadas); o nome e o IBGE daqui ficam.
    instancia = carga.instancia_atual
    for campo in list(dados):
        if campo not in ("latitude", "longitude", "capital") or instancia is None:
            dados.pop(campo, None)
        elif getattr(instancia, campo) not in (None, "", False):
            dados.pop(campo, None)


def _nada(dados, linha, carga):
    dados.clear()


def _ajustar_configuracao(dados, linha, carga):
    # A configuração é uma só aqui: o GV preenche o que tem, e o que está
    # vazio lá não apaga o que já está preenchido aqui (órgão, endereço...).
    for campo in [k for k, v in dados.items() if v in (None, "")]:
        dados.pop(campo)


def _viagem(dados, linha, carga):
    uf = (linha.get("destino_uf") or "").upper()
    municipio = carga.municipio_por_nome(linha.get("destino_cidade"), uf)
    dados["destino_municipio_id"] = municipio.pk if municipio else None
    dados["destino_estado_id"] = municipio.estado_id if municipio else carga.estado_por_sigla(uf)
    dados["cancelado"] = (linha.get("status") or "").lower() == "cancelado" or bool(linha.get("cancelado_em"))


def _rota(manual, calculada):
    return lambda linha, carga: linha.get(manual) if linha.get(manual) is not None else linha.get(calculada)


def _cidade(coluna):
    return lambda linha, carga: carga.traduzir("cadastros_cidade", linha.get(coluna))


def _evento(linha, carga):
    return carga.traduzir("eventos_evento", linha.get("evento_id"))


TABELAS = [
    # Referências: só se vincula ao que já existe aqui.
    Tabela("auth_user", "accounts.User", existente=_usuario, so_vincular=True, ajustar=_nada),
    Tabela("cadastros_estado", "cadastros.Estado", existente=_estado, so_vincular=True, ajustar=_nada),
    Tabela("cadastros_cidade", "cadastros.Municipio", existente=_municipio, so_vincular=True, ajustar=_ajustar_municipio),
    # Cadastros.
    Tabela("cadastros_cargo", "viagens_cadastros.Cargo", existente=_por_nome(), por_area=True),
    Tabela("cadastros_unidade", "viagens_cadastros.Unidade", existente=_por_nome(), por_area=True),
    Tabela("cadastros_combustivel", "viagens_cadastros.Combustivel", existente=_por_nome(), por_area=True),
    Tabela("cadastros_servidor", "viagens_cadastros.Servidor", existente=_servidor, ajustar=_ajustar_servidor, por_area=True),
    Tabela("cadastros_viatura", "viagens_cadastros.Viatura", existente=_viatura, ajustar=_ajustar_viatura, por_area=True,
           m2m=(("cadastros_viatura_motoristas", "motoristas"),)),
    Tabela("cadastros_tabeladiaria", "viagens_cadastros.TabelaDiaria", existente=_unicos),
    Tabela("cadastros_configuracaosistema", "viagens_cadastros.ConfiguracaoSistema", existente=_configuracao, por_area=True,
           ajustar=_ajustar_configuracao),
    Tabela("cadastros_assinaturaconfiguracao", "viagens_cadastros.AssinaturaConfiguracao", existente=_unicos),
    # Viagens (os "eventos" do GV).
    Tabela("eventos_tipoevento", "viagens_viagem.TipoViagem", existente=_por_nome(), por_area=True),
    Tabela("eventos_evento", "viagens_viagem.Viagem", ajustar=_viagem, por_area=True,
           m2m=(("eventos_evento_tipos", "tipos"),)),
    Tabela("eventos_eventodocumentosolicitacao", "viagens_viagem.ViagemDocumentoSolicitacao", colunas={"viagem_id": _evento}),
    # Roteiros.
    Tabela("roteiros_roteiro", "viagens_roteiros.Roteiro", por_area=True, colunas={
        "origem_municipio_id": _cidade("origem_cidade_id"),
        "viagem_id": _evento,
        "rota_distancia_km": _rota("rota_distancia_manual_km", "rota_distancia_calculada_km"),
        "rota_duracao_min": _rota("rota_duracao_manual_min", "rota_duracao_calculada_min"),
        "resumo_diarias": lambda linha, carga: linha.get("quantidade_diarias") or "",
    }),
    Tabela("roteiros_roteirodestino", "viagens_roteiros.RoteiroDestino", colunas={"municipio_id": _cidade("cidade_id")}),
    Tabela("roteiros_roteirotrecho", "viagens_roteiros.RoteiroTrecho", colunas={
        "origem_municipio_id": _cidade("origem_cidade_id"),
        "destino_municipio_id": _cidade("destino_cidade_id"),
        "sentido": lambda linha, carga: linha.get("tipo"),
        "duracao_min": lambda linha, carga: linha.get("duracao_estimada_min"),
        "tempo_viagem_min": lambda linha, carga: linha.get("tempo_cru_estimado_min"),
    }),
    Tabela("roteiros_roteirodiariacomponente", "viagens_roteiros.RoteiroDiariaComponente"),
    # Ofícios, justificativas e termos.
    Tabela("oficios_configuracaonumeracaooficio", "viagens_oficios.ConfiguracaoNumeracaoOficio", existente=_unicos, por_area=True),
    Tabela("oficios_modelomotivooficio", "viagens_oficios.ModeloMotivoOficio", existente=_por_nome(), por_area=True),
    Tabela("justificativas_modelojustificativa", "viagens_oficios.ModeloJustificativa", existente=_por_nome(), por_area=True),
    Tabela("oficios_oficio", "viagens_oficios.Oficio", por_area=True, colunas={"viagem_id": _evento},
           m2m=(("oficios_oficio_servidores", "servidores"), ("oficios_oficio_servidores_termo_autorizacao", "servidores_termo_autorizacao"))),
    Tabela("justificativas_justificativa", "viagens_oficios.Justificativa", existente=_unicos),
    Tabela("termos_termoautorizacao", "viagens_termos.TermoAutorizacao", por_area=True, colunas={"viagem_id": _evento},
           m2m=(("termos_termoautorizacao_servidores", "servidores"),)),
    # Ordens de serviço.
    Tabela("ordens_servico_ordemservico", "viagens_ordens.OrdemServico", por_area=True, colunas={"viagem_id": _evento},
           m2m=(("ordens_servico_ordemservico_destinos", "destinos"), ("ordens_servico_ordemservico_oficios", "oficios"),
                ("ordens_servico_ordemservico_servidores", "servidores"))),
    Tabela("ordens_servico_ordemserviconumerolacuna", "viagens_ordens.OrdemServicoNumeroLacuna", existente=_unicos, por_area=True),
    # Planos de trabalho.
    Tabela("planos_trabalho_programasolicitante", "viagens_planos.ProgramaSolicitante", existente=_por_nome(), por_area=True),
    Tabela("planos_trabalho_horarioatendimento", "viagens_planos.HorarioAtendimento", existente=_por_nome("faixa"), por_area=True),
    Tabela("planos_trabalho_atividadeplanotrabalho", "viagens_planos.AtividadePlanoTrabalho", existente=_unicos, por_area=True),
    Tabela("planos_trabalho_presetatividadesplanotrabalho", "viagens_planos.PresetAtividadesPlanoTrabalho", existente=_por_nome(), por_area=True,
           m2m=(("planos_trabalho_presetatividadesplanotrabalho_atividades", "atividades"),)),
    Tabela("planos_trabalho_planotrabalho", "viagens_planos.PlanoTrabalho", por_area=True, colunas={"viagem_id": _evento},
           m2m=(("planos_trabalho_planotrabalho_atividades_selecionadas", "atividades_selecionadas"),)),
    Tabela("planos_trabalho_eventoplano", "viagens_planos.EventoPlano",
           m2m=(("planos_trabalho_eventoplano_atividades_selecionadas", "atividades_selecionadas"),)),
    Tabela("planos_trabalho_planodestino", "viagens_planos.PlanoDestino"),
    Tabela("planos_trabalho_efetivoplano", "viagens_planos.EfetivoPlano"),
    # Prestações de contas.
    Tabela("prestacoes_contas_prestacaocontas", "viagens_prestacoes.PrestacaoContas", existente=_unicos, por_area=True),
    Tabela("prestacoes_contas_prestacaoservidor", "viagens_prestacoes.PrestacaoServidor", existente=_unicos),
    Tabela("prestacoes_contas_relatoriotecnico", "viagens_prestacoes.RelatorioTecnico", existente=_unicos),
    Tabela("prestacoes_contas_diariobordo", "viagens_prestacoes.DiarioBordo", existente=_unicos),
    Tabela("prestacoes_contas_diariobordotrecho", "viagens_prestacoes.DiarioBordoTrecho"),
    Tabela("prestacoes_contas_prestacaodocumentoanexo", "viagens_prestacoes.PrestacaoDocumentoAnexo"),
    Tabela("prestacoes_contas_carimbosolicitacao", "viagens_prestacoes.CarimboSolicitacao"),
    # Documentos gerados e assinados.
    Tabela("documentos_documentoartefato", "documentos.DocumentoArtefato", por_area=True),
    Tabela("documentos_documentoassinaturaversao", "documentos.DocumentoAssinaturaVersao"),
]

# Tabela do GV de cada modelo daqui: as FKs são traduzidas por ela.
TABELA_DO_MODELO = {t.modelo: t.nome for t in TABELAS}
TIMESTAMPS = {"criado_em": ("created_at", "criado_em"), "atualizado_em": ("updated_at", "atualizado_em")}


class Carga:
    def __init__(self, origem, *, lote, areas, media_gv, commit, copiar_arquivos, saida=print):
        self.origem = origem
        self.lote = lote
        self.areas = set(areas)
        self.media_gv = Path(media_gv) if media_gv else None
        self.commit = commit
        self.copiar_arquivos = copiar_arquivos
        self.saida = saida
        self.mapa = defaultdict(dict)  # tabela do GV → {id na origem: pk aqui}
        self.pendentes = []  # FKs que apontam para linha ainda não trazida
        self.relatorios = {}
        self.sigla_do_estado = {}
        self._municipios = None
        self.modelo_atual = None
        self.instancia_atual = None

    # ---- Traduções ---------------------------------------------------------
    def traduzir(self, tabela, origem_pk):
        if origem_pk in (None, ""):
            return None
        return self.mapa[tabela].get(str(origem_pk))

    def municipio_por_nome(self, nome, uf):
        from cadastros.models import Municipio

        if self._municipios is None:
            self._municipios = {}
            for m in Municipio.objects.select_related("estado"):
                self._municipios.setdefault((normalizar(m.nome), m.estado.sigla.upper()), m)
        return self._municipios.get((normalizar(nome), (uf or "").upper())) if nome else None

    def estado_por_sigla(self, sigla):
        from cadastros.models import Estado

        achado = Estado.objects.filter(sigla__iexact=sigla or "").first()
        return achado.pk if achado else None

    # ---- Leitura -----------------------------------------------------------
    def linhas(self, tabela):
        linhas = self.origem.linhas(tabela.nome)
        if tabela.por_area and linhas and "area_id" in linhas[0]:
            linhas = [l for l in linhas if l.get("area_id") in self.areas or l.get("area_id") is None]
        return linhas

    # ---- Uma tabela --------------------------------------------------------
    def executar(self):
        from .models import Registro

        # O que já foi trazido antes: o diário é o mapa inicial.
        for registro in Registro.objects.exclude(etapa="nativo"):
            self.mapa[registro.tabela][registro.origem_pk] = registro.destino_pk
        for linha in self.origem.linhas("cadastros_estado"):
            self.sigla_do_estado[linha["id"]] = (linha.get("sigla") or "").upper()
        for tabela in TABELAS:
            self.relatorios[tabela.nome] = self.carregar(tabela)
        self.resolver_pendentes()
        return self.relatorios

    def carregar(self, tabela):
        from .models import Registro

        modelo = apps.get_model(tabela.modelo)
        self.modelo_atual = modelo
        relatorio = Relatorio()
        campos = [f for f in modelo._meta.concrete_fields if not f.primary_key and not f.name.startswith("legado_")]
        for linha in self.linhas(tabela):
            origem_pk = str(linha["id"])
            try:
                with transaction.atomic():
                    self.carregar_linha(tabela, modelo, campos, linha, origem_pk, relatorio)
            except (IntegrityError, DataError, ValidationError, ValueError) as exc:
                relatorio.reprovadas.append({"id": origem_pk, "motivo": str(exc).splitlines()[0][:300]})
        for tabela_m2m, nome_campo in tabela.m2m:
            relatorio.vinculos_m2m += self.carregar_m2m(tabela, modelo, tabela_m2m, nome_campo, relatorio)
        self.saida(f"  {tabela.nome:55s} -> {tabela.modelo:40s} "
                   f"criadas {relatorio.criadas:4d}  vinculadas {relatorio.vinculadas:4d}  atualizadas {relatorio.atualizadas:4d}  "
                   f"reprovadas {len(relatorio.reprovadas):3d}" + (f"  m2m {relatorio.vinculos_m2m}" if tabela.m2m else ""))
        return relatorio.como_dict()

    def carregar_linha(self, tabela, modelo, campos, linha, origem_pk, relatorio):
        from .models import Registro

        # Onde a linha já está aqui: no diário, ou um registro igual.
        destino_pk = self.mapa[tabela.nome].get(origem_pk)
        instancia = modelo._base_manager.filter(pk=destino_pk).first() if destino_pk else None
        dados = self.montar(tabela, modelo, campos, linha, relatorio)
        self.instancia_atual = instancia
        if instancia is None and tabela.existente:
            instancia = tabela.existente(dados, linha, self)
            self.instancia_atual = instancia
        if tabela.ajustar:
            tabela.ajustar(dados, linha, self)
        if tabela.so_vincular:
            if instancia is None:
                relatorio.reprovadas.append({"id": origem_pk, "motivo": "sem correspondente aqui (não se cria)"})
                return
            if dados:
                modelo._base_manager.filter(pk=instancia.pk).update(**dados)
            self.mapa[tabela.nome][origem_pk] = str(instancia.pk)
            relatorio.vinculadas += 1
            return

        timestamps = {k: v for k, v in dados.items() if k in TIMESTAMPS}
        if instancia is None:
            self.abrir_espaco(tabela, modelo, dados)
            objeto = modelo(**{k: v for k, v in dados.items() if k not in TIMESTAMPS}, **self.marca_de_origem(modelo, linha["id"]))
            modelo._base_manager.bulk_create([objeto])
            if timestamps:
                modelo._base_manager.filter(pk=objeto.pk).update(**timestamps)
            criado, antes = True, {}
            relatorio.criadas += 1
            destino = objeto.pk
        else:
            existente_no_diario = Registro.objects.filter(tabela=tabela.nome, origem_pk=origem_pk).first()
            antes = existente_no_diario.antes if existente_no_diario else {
                k: _json(getattr(instancia, k)) for k in dados if k not in TIMESTAMPS and getattr(instancia, k) != dados[k]
            }
            criado = bool(existente_no_diario and existente_no_diario.criado)
            modelo._base_manager.filter(pk=instancia.pk).update(**{k: v for k, v in dados.items() if not (k in TIMESTAMPS and not criado)})
            destino = instancia.pk
            if existente_no_diario:
                relatorio.atualizadas += 1
            else:
                relatorio.vinculadas += 1
        self.mapa[tabela.nome][origem_pk] = str(destino)
        Registro.objects.update_or_create(tabela=tabela.nome, origem_pk=origem_pk, defaults={
            "lote": self.lote, "etapa": tabela.nome.split("_")[0], "modelo": tabela.modelo, "destino_pk": str(destino),
            "criado": criado, "antes": antes, "depois": {},
            "fingerprint": hashlib.sha256(json.dumps(linha, default=_json, sort_keys=True).encode()).hexdigest(),
        })

    def abrir_espaco(self, tabela, modelo, dados):
        """O que é do GV fica como era lá; o que já estava aqui cede:

        - catálogo com um item padrão (cargo, combustível, modelo de motivo):
          o padrão do GV passa a ser o padrão, e o daqui deixa de ser;
        - número do ano (ofício, OS, plano): o registro daqui que ocupa o
          número de um do GV vai para um número alto (+900000).

        Cada mudança num registro daqui entra no diário (com o valor de
        antes), para desfazer."""
        nomes = {f.name for f in modelo._meta.concrete_fields}
        if dados.get("is_padrao") and "is_padrao" in nomes:
            for outro in modelo._base_manager.filter(is_padrao=True):
                self.anotar_nativo(tabela, modelo, outro, {"is_padrao": True})
                modelo._base_manager.filter(pk=outro.pk).update(is_padrao=False)
        if {"numero", "ano"} <= nomes and dados.get("numero") and dados.get("ano"):
            ocupante = modelo._base_manager.filter(numero=dados["numero"], ano=dados["ano"]).first()
            if ocupante is not None:
                self.anotar_nativo(tabela, modelo, ocupante, {"numero": ocupante.numero})
                modelo._base_manager.filter(pk=ocupante.pk).update(numero=ocupante.numero + 900000)
                self.relatorios.setdefault("_renumerados", []).append(
                    f"{modelo._meta.label} #{ocupante.pk}: {ocupante.numero}/{ocupante.ano} -> {ocupante.numero + 900000}/{ocupante.ano}")

    def anotar_nativo(self, tabela, modelo, instancia, antes):
        """Mudança num registro que já estava aqui: o valor de antes, no diário."""
        from .models import Registro

        Registro.objects.get_or_create(
            tabela=f"{tabela.nome}#nativo", origem_pk=f"{modelo._meta.label}:{instancia.pk}:{','.join(antes)}",
            defaults={"lote": self.lote, "etapa": "nativo", "modelo": modelo._meta.label, "destino_pk": str(instancia.pk),
                      "criado": False, "antes": antes, "depois": {}, "fingerprint": ""},
        )

    @staticmethod
    def marca_de_origem(modelo, valor):
        """`legado_origem`/`legado_pk`, nos modelos que os têm (o diário da
        carga guarda a origem de todos)."""
        try:
            campo = modelo._meta.get_field("legado_pk")
        except Exception:
            return {}
        return {"legado_origem": ORIGEM, "legado_pk": valor if isinstance(campo, models.UUIDField) else int(valor)}

    def montar(self, tabela, modelo, campos, linha, relatorio):
        """Os valores daqui a partir da linha do GV: colunas de mesmo nome,
        as renomeadas, as FKs traduzidas pelo mapa e os arquivos copiados."""
        dados = {}
        for f in campos:
            coluna = f.column
            regra = tabela.colunas.get(coluna)
            if callable(regra):
                dados[f.attname] = regra(linha, self)
                continue
            origem_col = regra or coluna
            if f.name in TIMESTAMPS:
                valor = next((linha[c] for c in TIMESTAMPS[f.name] if c in linha), None)
                if valor is not None:
                    dados[f.name] = valor
                continue
            if origem_col not in linha:
                continue
            valor = linha[origem_col]
            if f.is_relation:
                alvo = TABELA_DO_MODELO.get(f.related_model._meta.label)
                traduzido = self.traduzir(alvo, valor) if alvo else None
                if valor is not None and traduzido is None:
                    if not f.null:
                        raise ValueError(f"{f.name}: {alvo or f.related_model._meta.label} #{valor} não foi trazido")
                    self.pendentes.append((modelo, f.attname, alvo, valor, linha["id"], tabela.nome))
                dados[f.attname] = traduzido
            elif isinstance(f, models.FileField):
                dados[f.attname] = self.arquivo(valor, relatorio)
            else:
                if valor is None and not f.null:
                    continue  # o padrão daqui vale
                dados[f.attname] = valor
        return dados

    def arquivo(self, nome, relatorio):
        from .arquivos import copiar_arquivo, planejar_arquivo, quarentenar

        if not nome:
            return ""
        if not self.copiar_arquivos or self.media_gv is None:
            relatorio.arquivos["nao_copiados"] += 1
            return ""
        try:
            plano = planejar_arquivo(self.media_gv, nome, extensoes=EXTENSOES)
        except ValidationError as exc:
            relatorio.arquivos["quarentena"] += 1
            relatorio.reprovadas.append({"arquivo": nome, "motivo": "; ".join(exc.messages)})
            quarentenar(self.media_gv, nome, Path(settings.MEDIA_ROOT).parent / "quarentena_legado", commit=self.commit)
            return ""
        if not self.commit:
            relatorio.arquivos["a_copiar"] += 1
            return plano.nome
        nome_final, criado = copiar_arquivo(plano, settings.MEDIA_ROOT)
        relatorio.arquivos["copiados" if criado else "ja_existiam"] += 1
        return nome_final

    def carregar_m2m(self, tabela, modelo, tabela_m2m, nome_campo, relatorio):
        campo = modelo._meta.get_field(nome_campo)
        through = campo.remote_field.through
        colunas_aqui = [f for f in through._meta.concrete_fields if not f.primary_key]
        dono, alvo = colunas_aqui[0], colunas_aqui[1]
        if dono.related_model is not modelo:
            dono, alvo = alvo, dono
        tabela_alvo = TABELA_DO_MODELO.get(alvo.related_model._meta.label)
        novos = 0
        for linha in self.origem.linhas(tabela_m2m):
            colunas = [c for c in linha if c != "id"]
            origem_dono, origem_alvo = linha[colunas[0]], linha[colunas[1]]
            pk_dono = self.traduzir(tabela.nome, origem_dono)
            pk_alvo = self.traduzir(tabela_alvo, origem_alvo)
            if pk_dono is None:
                continue  # o dono não veio (outra área, reprovado)
            if pk_alvo is None:
                relatorio.reprovadas.append({"m2m": tabela_m2m, "motivo": f"{tabela_alvo} #{origem_alvo} não foi trazido"})
                continue
            _, criado = through._base_manager.get_or_create(**{dono.attname: pk_dono, alvo.attname: pk_alvo})
            novos += int(criado)
        return novos

    def resolver_pendentes(self):
        """FKs para linhas que vieram depois (ou de si mesmas): segunda passada."""
        for modelo, attname, alvo, valor, origem_pk, tabela in self.pendentes:
            pk = self.traduzir(tabela, origem_pk)
            destino = self.traduzir(alvo, valor)
            if pk and destino:
                modelo._base_manager.filter(pk=pk).update(**{attname: destino})
            elif pk:
                self.relatorios.setdefault("_pendentes", {"sem_destino": []})["sem_destino"].append(f"{tabela}#{origem_pk}.{attname} → {alvo}#{valor}")

"""Converte o cadastro de motoristas em servidores do domínio de viagens.

Motorista deixa de ser uma tabela própria: quem dirige é um servidor com o
cargo MOTORISTA. Manter duas tabelas de pessoa fazia o mesmo servidor existir
duas vezes, com grafias diferentes e sem CPF em uma delas.

A conversão é **idempotente e reversível**: cada servidor criado guarda de onde
veio (`legado_origem`/`legado_pk`), reexecutar reaproveita o que já existe, e a
reversão recria os motoristas a partir desse mesmo rastro.

Dois motoristas cujo nome só difere em caixa ou espaçamento ("José Silva" e
"JOSÉ  SILVA") normalizam para o mesmo texto: são a mesma pessoa cadastrada
duas vezes, então viram **um** servidor e as duas solicitações apontam para ele.

Só dados — nenhuma alteração de esquema aqui, pelo motivo explicado em `0017`.
"""

from django.db import migrations

ORIGEM = "cadastros.Motorista"
CARGO_MOTORISTA = "MOTORISTA"


def _maiusculas(valor):
    return " ".join((valor or "").strip().split()).upper()


def _digitos(valor):
    return "".join(c for c in (valor or "") if c.isdigit())


def converter(apps, schema_editor):
    Motorista = apps.get_model("cadastros", "Motorista")
    Servidor = apps.get_model("viagens_cadastros", "Servidor")
    Cargo = apps.get_model("viagens_cadastros", "Cargo")
    Solicitacao = apps.get_model("solicitacoes", "SolicitacaoEvento")

    motoristas = list(Motorista.objects.all())
    if not motoristas:
        return

    cargo, _ = Cargo.objects.get_or_create(
        nome=CARGO_MOTORISTA, defaults={"is_padrao": False, "ativo": True}
    )

    # Telefones já usados: a unicidade é global, e telefone repetido no legado
    # não pode derrubar a migração inteira — o segundo fica sem telefone.
    telefones_ocupados = set(
        Servidor.objects.exclude(telefone="").values_list("telefone", flat=True)
    )
    mapa = {}
    por_nome = {}

    def _telefone_utilizavel(motorista):
        telefone = _digitos(getattr(motorista, "telefone", ""))
        if len(telefone) not in (10, 11) or telefone in telefones_ocupados:
            return ""
        return telefone

    def _fundir(servidor, motorista):
        """Une o que a duplicata tem e o servidor não.

        Sem isto o resultado dependeria da ordem em que as linhas saem do
        banco: o cadastro sem telefone poderia vir primeiro e o telefone do
        outro seria descartado em silêncio.
        """
        mudou = []
        if not servidor.telefone:
            telefone = _telefone_utilizavel(motorista)
            if telefone:
                servidor.telefone = telefone
                telefones_ocupados.add(telefone)
                mudou.append("telefone")
        # Basta uma das linhas estar ativa para a pessoa estar ativa.
        if getattr(motorista, "ativo", True) and not servidor.ativo:
            servidor.ativo = True
            mudou.append("ativo")
        if mudou:
            servidor.save(update_fields=mudou)

    for motorista in motoristas:
        nome = _maiusculas(motorista.nome) or f"MOTORISTA {motorista.pk}"

        existente = Servidor.objects.filter(
            legado_origem=ORIGEM, legado_pk=motorista.pk
        ).first()
        if existente is not None:
            mapa[motorista.pk] = existente
            por_nome.setdefault(nome, existente)
            continue

        # Mesma pessoa cadastrada duas vezes no legado: reaproveita o servidor
        # e absorve o que só a duplicata tinha.
        if nome in por_nome:
            servidor = por_nome[nome]
            _fundir(servidor, motorista)
            mapa[motorista.pk] = servidor
            continue
        ja_existe = Servidor.objects.filter(nome=nome).first()
        if ja_existe is not None:
            _fundir(ja_existe, motorista)
            mapa[motorista.pk] = ja_existe
            por_nome[nome] = ja_existe
            continue

        telefone = _telefone_utilizavel(motorista)
        if telefone:
            telefones_ocupados.add(telefone)

        servidor = Servidor.objects.create(
            nome=nome,
            cargo=cargo,
            telefone=telefone,
            ativo=getattr(motorista, "ativo", True),
            # Sem CPF nem RG no cadastro de origem: o servidor nasce como
            # rascunho e é completado pela tela.
            cpf="",
            rg="NAO POSSUI RG",
            sem_rg=True,
            status="RASCUNHO",
            legado_origem=ORIGEM,
            legado_pk=motorista.pk,
        )
        mapa[motorista.pk] = servidor
        por_nome[nome] = servidor

    # Um UPDATE por servidor, e não por solicitação: são poucos motoristas e
    # muitas solicitações.
    for motorista_id, servidor in mapa.items():
        Solicitacao.objects.filter(motorista_id=motorista_id).update(
            motorista_servidor=servidor
        )


def _ressincronizar_sequencia(schema_editor, Motorista):
    """Recoloca a sequência da tabela acima do maior id inserido à mão.

    Reverter recria os motoristas com pk explícito, e no PostgreSQL isso não
    avança a sequência: ela continua em 1, e o primeiro cadastro novo feito
    depois do rollback colidiria com uma linha existente. Em bancos sem
    sequência (SQLite) não há o que fazer.
    """
    conexao = schema_editor.connection
    if conexao.vendor != "postgresql":
        return
    tabela = Motorista._meta.db_table
    with conexao.cursor() as cursor:
        cursor.execute(
            f"SELECT setval(pg_get_serial_sequence(%s, 'id'), "
            f"COALESCE((SELECT MAX(id) FROM {tabela}), 1))",
            [tabela],
        )


def reverter(apps, schema_editor):
    """Recria os motoristas a partir do rastro e devolve os vínculos."""
    Motorista = apps.get_model("cadastros", "Motorista")
    Servidor = apps.get_model("viagens_cadastros", "Servidor")
    Solicitacao = apps.get_model("solicitacoes", "SolicitacaoEvento")

    for servidor in Servidor.objects.filter(
        legado_origem=ORIGEM, legado_pk__isnull=False
    ):
        motorista, _ = Motorista.objects.get_or_create(
            pk=servidor.legado_pk,
            defaults={
                "nome": servidor.nome,
                "telefone": servidor.telefone,
                "ativo": servidor.ativo,
            },
        )
        Solicitacao.objects.filter(motorista_servidor_id=servidor.pk).update(
            motorista=motorista
        )

    _ressincronizar_sequencia(schema_editor, Motorista)


class Migration(migrations.Migration):

    dependencies = [
        ("cadastros", "0007_normaliza_nomes_em_caixa_alta"),
        ("solicitacoes", "0017_adiciona_motorista_servidor"),
        ("viagens_cadastros", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(converter, reverter),
    ]

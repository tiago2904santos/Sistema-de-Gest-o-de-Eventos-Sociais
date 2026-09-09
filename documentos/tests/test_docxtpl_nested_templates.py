"""Smoke tests dos modelos DOCX com placeholders aninhados (Jinja no docxtpl)."""

from __future__ import annotations

from django.test import SimpleTestCase

from documentos.services.adapters.docxtpl_render import render_docx_bytes
from documentos.services.resources_paths import resolve_resource_docx


class DocxtplNestedTemplatesSmokeTests(SimpleTestCase):



    def test_termo_autorizacao_docx_renders(self):
        path = resolve_resource_docx("termo_autorizacao.docx")
        self.assertTrue(path.is_file())
        out = render_docx_bytes(
            template_path=path,
            context={
                "institucional": {
                    "unidade": "Unidade Teste",
                    "sede": "Curitiba",
                    "cidade_endereco": "Curitiba",
                    "nome_chefia": "Chefia Teste",
                    "cargo_chefia": "Delegado",
                },
                "oficio": {"numero_formatado": "10/2026"},
                "termo": {
                    "participante": {
                        "nome": "Servidor Teste",
                        "cargo": "Investigador",
                        "rg_formatado": "1.234.567",
                        "cpf": "00000000000",
                        "cpf_formatado": "000.000.000-00",
                        "unidade": "Unidade Teste",
                        "telefone_formatado": "(41) 99999-9999",
                    },
                    "oficio": {
                        "numero_formatado": "10/2026",
                        "protocolo_formatado": "12.345.678-1",
                        "data_criacao": "12/05/2026",
                        "assunto": "Viagem institucional",
                        "origem": "Unidade Teste",
                        "destino": "Chefia competente",
                    },
                    "viagem": {
                        "destino_principal": "Londrina/PR",
                        "destinos_texto": "Londrina/PR",
                        "periodo": "13/05/2026 08:00 a 15/05/2026 21:00",
                        "roteiro_ida_texto": "Curitiba/PR para Londrina/PR",
                        "roteiro_retorno_texto": "Londrina/PR para Curitiba/PR",
                        "quantidade_diarias": "2,5",
                        "valor_diarias": "R$ 1.250,00",
                        "valor_diarias_extenso": "mil duzentos e cinquenta reais",
                        "motivo": "Diligencia policial.",
                    },
                    "transporte": {
                        "tem_viatura": True,
                        "placa": "ABC-1234",
                        "modelo": "Duster",
                        "tipo": "Caracterizada",
                        "combustivel": "Gasolina",
                        "motorista": "Servidor Teste",
                        "porte_armas": "Sim",
                        "unidade": "Unidade Teste",
                    },
                    "textos": {
                        "titulo": "TERMO DE AUTORIZACAO",
                        "corpo_autorizacao": "Autorizo o deslocamento.",
                        "declaracao": "O servidor declara ciencia.",
                        "observacoes": "--",
                    },
                },
            },
        )
        self.assertTrue(out.startswith(b"PK"))

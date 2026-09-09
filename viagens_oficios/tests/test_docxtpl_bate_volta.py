from django.test import TestCase

from cadastros.models import Municipio as Cidade
from cadastros.models import Regiao
from cadastros.models import Estado
from viagens_oficios.docxtpl_context import build_oficio_docxtpl_context
from viagens_oficios.models import Oficio
from viagens_roteiros.models import Roteiro
from viagens_roteiros.models import RoteiroTrecho



class BateVoltaDocxtplTests(TestCase):
    """Roteiro bate-volta diário: idas e voltas devem ir para os blocos certos.

    No modo bate-volta os trechos são gravados como pares alternados
    ``sede → destino`` / ``destino → sede`` e apenas o último recebe
    ``tipo=RETORNO``. O documento não pode dividir por ``tipo`` (isso jogava as
    voltas intermediárias no ROTEIRO DE IDA).
    """

    def setUp(self):
        self.estado = Estado.objects.get_or_create(sigla="PR", defaults={"nome": "PARANA"})[0]
        self.sede = Cidade.objects.get_or_create(
            codigo_ibge=4106902, defaults={"nome": "CURITIBA", "estado": self.estado, "regiao": Regiao.objects.get_or_create(nome="Interior")[0]}
        )[0]
        self.destino = Cidade.objects.get_or_create(
            codigo_ibge=4114302, defaults={"nome": "MANDIRITUBA", "estado": self.estado, "regiao": Regiao.objects.get_or_create(nome="Interior")[0]}
        )[0]

    def _ida(self, roteiro, ordem, dia, tipo=RoteiroTrecho.Sentido.IDA):
        return RoteiroTrecho.objects.create(
            roteiro=roteiro,
            ordem=ordem,
            sentido=tipo,
            origem_municipio=self.sede,
            destino_municipio=self.destino,
            saida_dt=f"2026-08-0{dia} 08:00",
            chegada_dt=f"2026-08-0{dia} 09:00",
        )

    def _volta(self, roteiro, ordem, dia, tipo=RoteiroTrecho.Sentido.IDA):
        return RoteiroTrecho.objects.create(
            roteiro=roteiro,
            ordem=ordem,
            sentido=tipo,
            origem_municipio=self.destino,
            destino_municipio=self.sede,
            saida_dt=f"2026-08-0{dia} 17:00",
            chegada_dt=f"2026-08-0{dia} 18:00",
        )

    def _roteiro_dois_dias(self):
        roteiro = Roteiro.objects.create( 
            origem_municipio=self.sede,
        )
        self._ida(roteiro, 0, 6)
        self._volta(roteiro, 1, 6)
        self._ida(roteiro, 2, 7)
        # última volta é gravada como RETORNO
        self._volta(roteiro, 3, 7, tipo=RoteiroTrecho.Sentido.RETORNO)
        return roteiro

    def test_idas_e_voltas_separadas_por_direcao(self):
        roteiro = self._roteiro_dois_dias()
        oficio = Oficio.objects.create( roteiro=roteiro)

        ctx = build_oficio_docxtpl_context(oficio)

        # Bloco de IDA: só saídas de Curitiba, nos dois dias.
        self.assertEqual(ctx["col_ida_saida"].count("Saída Curitiba/PR"), 2)
        self.assertNotIn("Saída Mandirituba", ctx["col_ida_saida"])
        self.assertIn("06/08/2026 08:00", ctx["col_ida_saida"])
        self.assertIn("07/08/2026 08:00", ctx["col_ida_saida"])
        self.assertEqual(ctx["col_ida_chegada"].count("Chegada Mandirituba/PR"), 2)

        # Bloco de RETORNO: só saídas de Mandirituba, nos dois dias.
        self.assertEqual(ctx["col_volta_saida"].count("Saída Mandirituba/PR"), 2)
        self.assertNotIn("Saída Curitiba", ctx["col_volta_saida"])
        self.assertIn("06/08/2026 17:00", ctx["col_volta_saida"])
        self.assertIn("07/08/2026 17:00", ctx["col_volta_saida"])
        self.assertEqual(ctx["col_volta_chegada"].count("Chegada Curitiba/PR"), 2)

    def test_roteiro_comum_mantem_split_por_tipo(self):
        # sede -> destino (ida) e destino -> sede (retorno) simples.
        roteiro = Roteiro.objects.create( 
            origem_municipio=self.sede,
        )
        self._ida(roteiro, 0, 6)
        self._volta(roteiro, 1, 6, tipo=RoteiroTrecho.Sentido.RETORNO)
        oficio = Oficio.objects.create( roteiro=roteiro)

        ctx = build_oficio_docxtpl_context(oficio)

        self.assertIn("Saída Curitiba/PR", ctx["col_ida_saida"])
        self.assertIn("Saída Mandirituba/PR", ctx["col_volta_saida"])

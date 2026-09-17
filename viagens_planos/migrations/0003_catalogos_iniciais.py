"""Catálogos iniciais do plano de trabalho, os mesmos do Gerenciador de Viagens.

Seed idempotente: cada item entra só se ainda não existir. A instalação pode
apagar ou renomear depois — nada aqui volta sozinho.
"""

from django.db import migrations

PROGRAMAS = ["PROGRAMA PARANÁ EM AÇÃO", "PROGRAMA JUSTIÇA NO BAIRRO", "PCPR NA COMUNIDADE"]

HORARIOS = ["09:00 até 17:00", "08:00 até 16:00", "10:00 até 18:00"]

ATIVIDADES = [
    ("CIN", "Confecção da Carteira de Identidade Nacional (CIN)",
     "Ampliar o acesso ao documento oficial de identificação civil, garantindo cidadania e inclusão social à população atendida.",
     "Kit de captura biométrica, estação de atendimento, conectividade e equipe técnica para triagem e emissão."),
    ("BO", "Registro de Boletins de Ocorrência",
     "Possibilitar o atendimento imediato de demandas policiais, promovendo orientação e formalização de ocorrências no próprio evento.",
     "Posto de atendimento com sistema de registro, insumos administrativos e equipe para orientação ao cidadão."),
    ("AAC", "Emissão de Atestado de Antecedentes Criminais",
     "Facilitar a obtenção do documento, contribuindo para fins trabalhistas e demais necessidades legais dos cidadãos.",
     "Terminal com acesso aos sistemas institucionais, impressão e equipe de apoio para validação de dados."),
    ("PALESTRAS", "Palestras e orientações preventivas",
     "Desenvolver ações educativas voltadas à prevenção de crimes, conscientização sobre segurança pública e fortalecimento do vínculo comunitário.",
     "Espaço para apresentação, sistema de áudio, material didático e equipe de facilitação."),
    ("LUDICO", "Atividades lúdicas e educativas para crianças",
     "Promover aproximação institucional de forma didática, incentivando a cultura de respeito às leis e à cidadania desde a infância.",
     "Materiais lúdicos, apoio pedagógico e área segura para dinâmicas com crianças."),
    ("NOC", "Apresentação do trabalho do Núcleo de Operações com Cães (NOC)",
     "Demonstrar as atividades operacionais desenvolvidas pela unidade especializada da Polícia Civil do Paraná, evidenciando técnicas e capacidades institucionais.",
     "Área controlada para exibição operacional, equipe especializada, equipamentos de segurança e suporte logístico."),
    ("TATICO", "Exposição de material tático",
     "Apresentar equipamentos utilizados nas atividades policiais, proporcionando transparência e conhecimento sobre os recursos empregados pela instituição.",
     "Bancadas de exposição, controle de acesso, equipe de apresentação e sinalização informativa."),
    ("PAPILOSCOPIA", "Exposição da atividade de perícia papiloscópica",
     "Demonstrar os procedimentos técnicos de identificação humana, ressaltando a importância da papiloscopia na investigação criminal e na identificação civil.",
     "Estação demonstrativa, kits de coleta, materiais visuais e equipe técnica especializada."),
    ("VIATURAS", "Exposição de viaturas antigas e modernas",
     "Apresentar a evolução histórica e tecnológica dos veículos operacionais da instituição.",
     "Área de exposição, apoio de segurança patrimonial e equipe para conduzir apresentações ao público."),
    ("BANDA", "Apresentação da banda institucional",
     "Fortalecer a integração com a comunidade por meio de atividade cultural representativa da instituição.",
     "Estrutura de palco, sonorização, logística de montagem e suporte técnico para apresentação musical."),
    ("UNIDADE_MOVEL", "Unidade móvel (ônibus ou caminhão)",
     "Viabilizar a prestação descentralizada dos serviços acima descritos, assegurando estrutura adequada para atendimento ao público.",
     "Unidade móvel institucional, equipe de operação, energia, conectividade e manutenção de suporte."),
]


def criar(apps, schema_editor):
    Programa = apps.get_model("viagens_planos", "ProgramaSolicitante")
    Horario = apps.get_model("viagens_planos", "HorarioAtendimento")
    Atividade = apps.get_model("viagens_planos", "AtividadePlanoTrabalho")
    for nome in PROGRAMAS:
        Programa.objects.get_or_create(nome=nome)
    for faixa in HORARIOS:
        Horario.objects.get_or_create(faixa=faixa)
    for codigo, nome, meta, recurso in ATIVIDADES:
        Atividade.objects.get_or_create(codigo=codigo, defaults={"nome": nome, "meta": meta, "recurso_necessario": recurso})


def remover(apps, schema_editor):
    # Os dados são da instalação: a volta da migração não os apaga.
    pass


class Migration(migrations.Migration):
    dependencies = [("viagens_planos", "0002_initial")]
    operations = [migrations.RunPython(criar, remover)]

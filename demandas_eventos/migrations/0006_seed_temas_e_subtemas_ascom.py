from django.db import migrations


CATALOGO = {
    "Proteção de crianças e adolescentes": (
        "Abuso sexual infantil, violência infantil, pedofilia e prevenção.",
        ["Abuso sexual infantil", "Violência infantil", "Pedofilia", "Prevenção da violência infantil"],
    ),
    "Bullying e cyberbullying": (
        "Prevenção, identificação e enfrentamento no ambiente escolar e digital.",
        ["Bullying", "Cyberbullying", "Prevenção e enfrentamento"],
    ),
    "Segurança digital e crimes cibernéticos": (
        "Crimes virtuais, internet segura, privacidade e uso consciente da tecnologia.",
        ["Crimes virtuais", "Internet segura", "Privacidade digital", "Uso consciente da tecnologia"],
    ),
    "Prevenção a golpes, fraudes e estelionatos": (
        "Estelionato, golpes presenciais ou digitais e orientação preventiva.",
        ["Estelionato", "Golpes presenciais", "Golpes digitais", "Orientação preventiva"],
    ),
    "Prevenção ao uso de álcool e outras drogas": (
        "Prevenção, saúde e impactos do uso de substâncias.",
        ["Prevenção ao uso de substâncias", "Saúde e uso de substâncias", "Impactos do uso de substâncias"],
    ),
    "Educação e segurança no trânsito": (
        "Acidentes, sinistros, crimes de trânsito e condução segura.",
        ["Acidentes e sinistros de trânsito", "Crimes de trânsito", "Condução segura"],
    ),
    "Enfrentamento à violência contra a mulher": (
        "Violência doméstica, direitos, denúncia e rede de proteção.",
        ["Violência doméstica", "Direitos e rede de proteção", "Denúncia e orientação"],
    ),
    "Prevenção ao assédio": (
        "Assédio moral, sexual e importunação, especialmente no trabalho.",
        ["Assédio moral", "Assédio sexual", "Importunação sexual"],
    ),
    "Prevenção à violência contra a pessoa idosa": (
        "Violência, golpes e orientação de proteção à pessoa idosa.",
        ["Violência contra a pessoa idosa", "Golpes contra a pessoa idosa", "Orientação de proteção"],
    ),
    "Direitos humanos, diversidade e cidadania": (
        "Direitos humanos, racismo, homofobia e cidadania.",
        ["Direitos humanos", "Racismo", "Homofobia", "Cidadania"],
    ),
    "Saúde mental e bem-estar": (
        "Saúde mental, qualidade de vida e apoio preventivo.",
        ["Saúde mental", "Qualidade de vida", "Apoio preventivo"],
    ),
    "Segurança pública e Polícia Civil": (
        "Profissão policial, segurança pública, polícia judiciária e investigação.",
        ["Profissão policial", "Segurança pública", "Polícia judiciária", "Investigação"],
    ),
    "Proteção aos animais": (
        "Maus-tratos e orientação de proteção animal.",
        ["Maus-tratos contra animais", "Proteção animal"],
    ),
    "Prevenção de acidentes e primeiros socorros": (
        "Acidentes domésticos, de trabalho e primeiros socorros.",
        ["Acidentes domésticos", "Acidentes de trabalho", "Primeiros socorros"],
    ),
    "Segurança pessoal": (
        "Autoproteção, prevenção e orientação de segurança.",
        ["Autoproteção", "Orientação de segurança"],
    ),
}


def cadastrar_catalogo(apps, schema_editor):
    Tema = apps.get_model("demandas_eventos", "Tema")
    Subtema = apps.get_model("demandas_eventos", "Subtema")

    for nome_tema, (escopo, subtemas) in CATALOGO.items():
        tema, _ = Tema.objects.get_or_create(nome=nome_tema, defaults={"ativo": True})
        if not tema.ativo:
            tema.ativo = True
            tema.save(update_fields=["ativo"])
        for nome_subtema in subtemas:
            Subtema.objects.get_or_create(
                tema=tema,
                nome=nome_subtema,
                defaults={"escopo": escopo, "ativo": True},
            )


class Migration(migrations.Migration):

    dependencies = [
        ("demandas_eventos", "0005_subtema_demandaevento_subtema_and_more"),
    ]

    operations = [migrations.RunPython(cadastrar_catalogo, migrations.RunPython.noop)]

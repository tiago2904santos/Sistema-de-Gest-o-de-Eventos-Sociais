"""Tag de arquivo estático com cache-busting automático em desenvolvimento.

Em produção o `CompressedManifestStaticFilesStorage` já põe um hash no nome do
arquivo e nada mais é preciso. Em desenvolvimento o nome é fixo, e o navegador
insistia em servir o CSS antigo — antes disso, a versão era um número escrito
à mão no base.html que alguém precisava lembrar de incrementar a cada edição.
"""

from pathlib import Path

from django import template
from django.conf import settings
from django.templatetags.static import static

register = template.Library()


def _mtime(caminho):
    """Data de modificação do arquivo nos diretórios estáticos, se existir."""
    for diretorio in settings.STATICFILES_DIRS:
        arquivo = Path(diretorio) / caminho
        try:
            return int(arquivo.stat().st_mtime)
        except OSError:
            continue
    return None


@register.simple_tag
def estatico(caminho):
    """URL do arquivo estático, versionada pela modificação em DEBUG."""
    url = static(caminho)
    if not settings.DEBUG:
        return url
    versao = _mtime(caminho)
    return f"{url}?v={versao}" if versao else url

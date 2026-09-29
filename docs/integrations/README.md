# Integrações

Fonte: `ui-inventory/integrations.json`.

| Integração | Configuração | Padrão | No laboratório | Documentação |
|---|---|---|---|---|
| eProtocolo PR (Celepar) | `EPROTOCOLO_*` | mock (número simulado) | mock forçado | `../EPROTOCOLO_PROTOCOLO_AUTOMATICO.md` |
| OpenRouteService (rotas) | `OPENROUTESERVICE_API_KEY` | desligado sem chave | desligado | settings |
| OpenStreetMap/Nominatim (geocodificação) | `GEOCODIFICAR_SOB_DEMANDA` | ligado fora da suíte | desligado | settings |
| WhatsApp Cloud API | `WHATSAPP_*` | desligado | desligado | `.env.example` |
| Anthropic (assistente) | `ANTHROPIC_API_KEY`, `ASSISTENTE_LLM` | determinístico | determinístico | `.env.example` |
| SMTP | `EMAIL_*` | console | console | settings |
| Banco legado GV | `LEGADO_DB_*` | desligado; somente-leitura quando ligado | desligado | `migracao_legado/` |
| Motores de PDF | `DOCUMENTOS_*` | auto (Word COM → LibreOffice → WeasyPrint → fpdf2) | auto | `../FASE_3_NUCLEO_DOCUMENTAL.md` |

Regra: toda integração tem modo desligado/mock que mantém o sistema utilizável — preservar isso.

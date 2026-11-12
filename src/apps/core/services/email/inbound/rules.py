"""The classifier's rule tables: which headers, senders, subjects and phrases mark mail as automated.

Only header-level signals (and the auto-reply subject prefixes, which mail systems write themselves) put a message
in an automated class; phrases in the text only choose the subtype of a message already known to be an automatic
reply (or, with one of Exchange's rule markers, make it one), or add a hint to a human one. Everything is compared
case-insensitively; the phrases cover English, Spanish, French, German, Portuguese, Italian and Dutch.
"""

import re

# The classes, from the site's own mail to a person's (``classify`` tries them in this order).
OWN, BOUNCE, RECEIPT, AUTO_REPLY, LEFT_ORG = "own", "bounce", "receipt", "auto_reply", "left_org"
SYSTEM, BULK, SPAM, HUMAN = "system", "bulk", "spam", "human"
AUTOMATED = frozenset({OWN, BOUNCE, RECEIPT, AUTO_REPLY, LEFT_ORG, SYSTEM, BULK, SPAM})
LABELS = {
    OWN: "Sent from the site's own address",
    BOUNCE: "Bounce or delay report",
    RECEIPT: "Read or delivery receipt",
    AUTO_REPLY: "Automatic reply",
    LEFT_ORG: "Left the organisation / address changed",
    SYSTEM: "Other system mail",
    BULK: "List or bulk mail",
    SPAM: "Spam",
    HUMAN: "Human (or uncertain)",
}

# Exchange, Gmail, Outlook.com and other systems' automatic-reply subject prefixes, in several languages.
AUTO_REPLY_SUBJECT_RE = re.compile(
    r"^\s*(?:automatic reply|auto[ -]?reply|auto[ -]?response|"
    r"out of (?:the )?office(?: reply| autoreply)?|abwesenheitsnotiz|automatische antwort|"
    r"r[ée]ponse automatique|respuesta autom[áa]tica|fuera de la oficina|risposta automatica|"
    r"resposta autom[áa]tica|automatisch antwoord|afwezig|autosvar|automaattinen vastaus|"
    r"automatick[áa] odpov[ěe]ď|odpowied[źz] automatyczna|otomatik yan[ıi]t|автоматический ответ|"
    r"自动回复|自動回覆|自動応答|자동 회신)\s*[:：]",
    re.IGNORECASE,
)
# Subjects that are only a hint on their own (a person may write them too).
AUTO_REPLY_HINT_RE = re.compile(r"\b(?:out of (?:the )?office|on vacation|on leave|away from (?:my|the) )", re.I)
RECEIPT_SUBJECT_RE = re.compile(r"^\s*(?:read|not read|delivered|read receipt|lu|gelesen|le[íi]do)\s*:", re.I)
CALENDAR_SUBJECT_RE = re.compile(
    r"^\s*(?:accepted|declined|tentative|tentatively accepted|new time proposed|"
    r"angenommen|abgelehnt|mit vorbehalt|accept[ée]|refus[ée]|aceptado|rechazado)\s*:",
    re.IGNORECASE,
)

# Wording that says the person left, retired or changed address, or that the address is closed: the
# bounced-addresses evidence (counted only for a notice matched to the site's mail, and never beside an absence).
LEFT_ORG_RE = re.compile(
    r"\bno longer (?:with|at|employed|affiliated|part of|works?|working|in use|active|valid|available|checked|"
    r"monitored|being monitored)\b|\b(?:has|have) (?:left|retired|departed)\b|\bretired (?:from|as of|in|on)\b|"
    r"\bleft the (?:company|organi[sz]ation|university|college|firm|agency|district|school|department|city|county)\b|"
    r"\b(?:my|his|her|their) last day (?:at|with) |\blast day of (?:employment|work)\b|"
    r"\bnew e-?mail address\b|\bchanged (?:my|his|her|their) e-?mail\b|\bplease (?:update|use) (?:my|the) new\b|"
    r"\b(?:my|this) e-?mail (?:address )?(?:has changed|will be deactivated|is being retired)\b|"
    r"\b(?:account|mailbox|address|inbox) (?:is|has been|was|will be) (?:closed|deactivated|terminated|retired)\b|"
    r"\bya no (?:trabaja|labora|forma parte|pertenece|es parte|est[áa] (?:con|en)|se encuentra (?:con|en))\b|"
    r"\bdej[óo] de (?:trabajar|laborar|formar parte|pertenecer)\b|\bse jubil[óo]\b|"
    r"\b(?:correo|cuenta|direcci[óo]n)\b[^.\n]{0,40}?\bya no (?:est[áa]|es|se)\b|"
    r"\bnuev[oa] (?:correo|direcci[óo]n|e-?mail)\b|\bne (?:fait|travaille) plus\b|"
    r"\ba quitt[ée] (?:la soci[ée]t[ée]|l[’']entreprise|l[’']organisation|l[’']universit[ée]|nos services)\b|"
    r"\bn[’']est plus (?:en poste|actif|active|valide|utilis[ée]e?|consult[ée]e?)\b|\bnouvelle adresse\b|"
    r"\bnicht mehr (?:im unternehmen|bei|f[üu]r|t[äa]tig|besch[äa]ftigt|aktiv|g[üu]ltig)\b|"
    r"\b(?:hat|haben) (?:das unternehmen|die firma|uns) verlassen\b|\bausgeschieden\b|\bneue (?:e-?mail-?)?adresse\b|"
    r"\bn[ãa]o (?:trabalha|faz parte) mais\b|\bj[áa] n[ãa]o (?:trabalha|faz parte)\b|"
    r"\bdeixou a (?:empresa|organiza[çc][ãa]o|universidade)\b|\bnov[oa] (?:e-?mail|endere[çc]o)\b|"
    r"\bnon (?:lavora|fa) pi[ùu]\b|\bnon [èe] pi[ùu] (?:attiv|valid|in uso)|\bnuovo indirizzo\b|"
    r"\bha lasciato (?:l[’']azienda|la societ[àa]|l[’']universit[àa])\b|"
    r"\bniet meer (?:werkzaam|in dienst|actief)\b|\buit dienst\b|\bnieuwe? (?:e-?mail)?adres\b",
    re.IGNORECASE,
)
# Wording that says only that nobody reads the mailbox: a seasonal notice says so too, so it means "left" only in a
# notice that mentions no absence.
UNMONITORED_RE = re.compile(
    r"\b(?:is|are) not (?:being |currently )?(?:monitored|checked|read)\b|\bnot monitored\b|"
    r"\bno (?:es|est[áa]) (?:monitoreado|supervisado)\b|\bno se revisa\b|\bn[’']est pas (?:surveill|consult)[ée]e?\b|"
    r"\bwird nicht (?:gelesen|[üu]berwacht)\b",
    re.IGNORECASE,
)
# Wording of an absence with a return: out of office, vacation, leave, travel ("will return your call" is not one).
VACATION_RE = re.compile(
    r"\bout of (?:the )?office\b|\booo\b|\bon (?:vacation|holidays?|leave|annual leave|parental leave|maternity leave|"
    r"paternity leave|medical leave|sick leave|sabbatical|pto|business travel|a business trip)\b|"
    r"\baway from (?:the |my )?(?:office|desk|e-?mail)\b|\b(?:currently|presently) (?:away|traveling|travelling|out)\b|"
    r"\b(?:limited|no) access to (?:my )?e-?mail\b|\b(?:will|i[’']?ll) be back\b|\bback in the office\b|"
    r"\b(?:will|i[’']?ll) return (?:on|to the office|by|in|after)\b|\breturn(?:ing)? (?:to the office )?on\b|"
    r"\buntil (?:mon|tue|wed|thu|fri|sat|sun|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d{1,2}[/.-])|"
    r"\bfuera de (?:la )?oficina\b|\bde vacaciones\b|\b(?:estar[ée]|me encuentro|estoy) (?:fuera|ausente|de viaje|"
    r"de permiso|de licencia)\b|\b(?:regreso|regresar[ée]|volver[ée]|retorno) (?:el|a la oficina)\b|"
    r"\bacceso limitado (?:a mi|al) correo\b|\bhasta el (?:lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bado|"
    r"domingo|\d)|\babsente? (?:du bureau|jusqu)|\ben (?:cong[ée]s?|vacances|d[ée]placement)\b|\bhors du bureau\b|"
    r"\bde retour (?:le|au bureau|lundi|mardi|mercredi|jeudi|vendredi)\b|\bnicht im (?:b[üu]ro|haus)\b|"
    r"\bau[ßs]er haus\b|\babwesend\b|\bim urlaub\b|\bwieder (?:im b[üu]ro|erreichbar|da)\b|"
    r"\bfora do escrit[óo]rio\b|\bde f[ée]rias\b|\bvoltarei\b|\bestarei (?:fora|ausente)\b|\bfuori (?:ufficio|sede)\b|"
    r"\bin ferie\b|\bassente (?:fino|dal)\b|\brientrer[òo]\b|\bmet vakantie\b|\bniet op kantoor\b|\bafwezig\b|"
    r"\bweer aanwezig\b",
    re.IGNORECASE,
)
# Other systems' automatic acknowledgements, challenge-response and quarantine notices.
SYSTEM_TEXT_RE = re.compile(
    r"\b(?:this is an automated (?:message|response|reply|notification)|"
    r"(?:we|i) (?:have )?received your (?:message|request|e-?mail)|your (?:request|ticket|case) (?:#|number|id)|"
    r"(?:verify|confirm) (?:that )?you are (?:a )?human|held in quarantine|quarantined|"
    r"(?:message|messages) (?:have been|has been|were) (?:held|quarantined|blocked))",
    re.IGNORECASE,
)

REPORT_SENDERS = ("postmaster", "mailer-daemon", "mail-daemon", "maildaemon")
NOREPLY_RE = re.compile(
    r"^(?:no[-_.]?reply|do[-_.]?not[-_.]?reply|donotreply|notifications?|bounces?)(?:[-+._].*)?$", re.I
)
QUARANTINE_LOCAL_RE = re.compile(r"(?:quarantine|spam[-_.]?digest|postmaster-digest)", re.IGNORECASE)

# Headers an RFC 3834 automatic responder (or a vendor's) sets.
AUTO_REPLY_HEADERS = ("x-autoreply", "x-autorespond", "x-autoreply-from", "x-mail-autoreply")
# Exchange's markers on mail one of its Inbox rules or agents generated (a rule's automatic reply, a redirect): they
# make a message an automatic reply only with the wording of one, as a redirected message can be a person's.
EXCHANGE_RULE_HEADERS = ("x-ms-exchange-inbox-rules-loop", "x-ms-exchange-generated-message-source")
# Mailing lists (RFC 2369/2919, 8058)...
LIST_HEADERS = (
    "list-id",
    "list-post",
    "list-unsubscribe",
    "list-unsubscribe-post",
    "list-help",
    "list-owner",
    "list-subscribe",
    "list-archive",
)
# ...of which these say a list distributed the message (the others only that its sender offers a way out, which CRM
# and sales tools add to one-to-one mail too).
DISTRIBUTION_HEADERS = ("list-id", "list-post")
# The large email service providers' and CRMs' own headers (Salesforce's on mail sent from a CRM record too).
ESP_HEADERS = (
    "x-mailchimp-id",
    "x-mc-user",
    "x-campaign",
    "x-campaignid",
    "x-sg-eid",
    "x-sg-id",
    "x-mailgun-sid",
    "x-mailgun-tag",
    "x-ses-outgoing",
    "x-sfmc-stack",
    "x-mkto-mailingid",
    "x-hubspot-email",
    "x-constantcontact",
    "x-csa-complaints",
    "x-pm-message-id",
    "x-mandrill-user",
    "x-sfdc-lk",
    "x-sfdc-user",
    "x-msfbl",
)
BULK_PRECEDENCE = ("bulk", "list", "junk")

SCL_RE = re.compile(r"(?:^|;)\s*SCL\s*:\s*(-?\d+)", re.IGNORECASE)
# Exchange Online's bulk complaint level, in X-Microsoft-Antispam ("BCL:7;").
BCL_RE = re.compile(r"(?:^|;)\s*BCL\s*:\s*(\d+)", re.IGNORECASE)
SPAM_VERDICT_RE = re.compile(r"(?:^|;)\s*SFV\s*:\s*(?:SPM|SKS|SKB)\b", re.IGNORECASE)
AUTH_RESULT_RE = re.compile(r"\b(spf|dkim|dmarc|compauth)\s*=\s*([a-z]+)", re.IGNORECASE)
DKIM_PASS_DOMAIN_RE = re.compile(r"\bdkim\s*=\s*pass\b[^;]*?\bheader\.(?:d|i)\s*=\s*@?([A-Za-z0-9.-]+)", re.I)

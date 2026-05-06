"""Controlled research workflow agents for SAP IS-U KB candidates."""
from __future__ import annotations

import re
from io import BytesIO
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Iterable
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen

from pypdf import PdfReader

from src.research.agents.topic_catalog import find_topic_definition
from src.research.storage.research_repository import ResearchSource


MAX_FETCH_CHARS = 60_000
MAX_PDF_FETCH_BYTES = 5_000_000
MAX_RAW_EXCERPT_CHARS = 12_000
MAX_SEARCH_CHARS = 120_000

TIER_CONFIDENCE = {
    "A": 0.9,
    "B": 0.75,
    "C": 0.55,
    "D": 0.25,
}

KNOWN_SAP_OBJECTS = {
    "BUT000", "FKKVKP", "DFKKOP", "DFKKKO", "EVER", "EANL", "EVBS", "EUIHEAD",
    "EUILO", "EUITRANS", "EUIINSTLN", "EQUI", "EQUZ", "IFLOT", "ETDZ", "EGER",
    "EGERH", "EGERR", "EASTL", "EABL", "EABLG", "EABLH", "ERCH", "ERCHC",
    "ERDK", "ETRG", "DBERCHZ", "TE422", "TE420", "TE417", "EL31", "EL28",
    "EL01", "EL37", "EA00", "EA19", "EA26", "EA40", "EC50E", "ES31", "IQ03",
    "BP", "CIC0", "CAA1", "CAA2", "CAA3", "FPP1", "FPP2", "FPP3", "FP03",
    "FP04", "FP05", "FP06", "FPVA", "FPL9", "FPCJ", "ES32", "ES55", "WE05",
    "WE21", "DFKKOPK", "DFKKLOCKS",
    "ISU_S_MOVE_IN", "ISU_S_MOVE_OUT", "ISU_BILLING", "UTILMD", "MSCONS",
    "APERAK", "INVOIC", "REMADV", "CONTRL", "GPKE", "GELI", "GABI", "WIM",
    "MABIS", "MPES", "IDOC", "EDIDS", "EDIDC", "EDID4", "WE02", "WE19",
    "WE20", "BD87", "EIDESWTDOC", "EDEXTASK", "EDEXPROC", "EMMA", "BPEM",
    "API", "S4HANA", "FIORI", "ISU", "SPRO", "SM30", "SE18", "SE19", "SE24",
    "SE37", "SE80", "CMOD", "SMOD", "BADI", "BAPI", "FQEVENTS",
}
SAP_TABLE_OBJECTS = {
    "BUT000", "FKKVKP", "DFKKOP", "DFKKKO", "EVER", "EANL", "EVBS", "EUIHEAD",
    "EUILO", "EUITRANS", "EUIINSTLN", "EQUI", "EQUZ", "IFLOT", "ETDZ", "EGER",
    "EGERH", "EGERR", "EASTL", "EABL", "EABLG", "EABLH", "ERCH", "ERCHC",
    "ERDK", "ETRG", "DBERCHZ", "TE422", "TE420", "TE417", "DFKKOPK",
    "DFKKLOCKS", "EDIDS", "EDIDC", "EDID4", "EIDESWTDOC", "EDEXTASK", "EDEXPROC",
}
SAP_TRANSACTION_OBJECTS = {
    "BP", "CIC0", "CAA1", "CAA2", "CAA3", "FPP1", "FPP2", "FPP3", "FPL9",
    "FP03", "FP04", "FP05", "FP06", "FPVA", "FPCJ", "EL01", "EL28", "EL31",
    "EL37", "EA00", "EA19", "EA26", "EA40", "EC50E", "ES31", "ES32", "ES55",
    "IQ03", "WE02", "WE05", "WE19", "WE20", "WE21", "BD87", "EMMA", "SPRO",
    "SM30", "SE18", "SE19", "SE24", "SE37", "SE80", "CMOD", "SMOD", "FQEVENTS",
}

SAP_OBJECT_SEEDS = {
    "FKKVKP": {
        "title": "FKKVKP contract account partner data",
        "text": (
            "FKKVKP is commonly used in FI-CA and SAP IS-U analysis around contract account "
            "partner-specific data. In incident triage it is often checked together with "
            "business partner data in BUT000, open items in DFKKOP and utility contracts in EVER. "
            "Useful topics include contract account assignment, business partner linkage, "
            "move-in/move-out consistency and FI-CA account troubleshooting."
        ),
    },
    "BUT000": {
        "title": "BUT000 business partner master data",
        "text": (
            "BUT000 contains central business partner master data. In SAP IS-U it is typically "
            "used with FI-CA contract account data such as FKKVKP and utility contract data such "
            "as EVER when analyzing customer, move-in or account inconsistencies."
        ),
    },
    "EVER": {
        "title": "EVER utility contract master data",
        "text": (
            "EVER is a core SAP IS-U contract table. It is relevant for move-in, move-out, billing, "
            "contract account assignment and installation-related incident analysis. Typical related "
            "objects include EANL for installations, FKKVKP for contract accounts and ERCH/ERDK for billing."
        ),
    },
    "EANL": {
        "title": "EANL installation master data",
        "text": (
            "EANL is used for SAP IS-U installation master data. It is central in device, meter reading, "
            "billing and premise/POD analysis. It is commonly reviewed with EVBS, EUIHEAD, EVER, EASTL and EGERH."
        ),
    },
    "EVBS": {
        "title": "EVBS premise master data",
        "text": (
            "EVBS represents premise master data in SAP IS-U. It is relevant when investigating POD, "
            "installation, move-in and address-related consistency issues."
        ),
    },
    "EUIHEAD": {
        "title": "EUIHEAD point of delivery data",
        "text": (
            "EUIHEAD is relevant for point of delivery and external/internal identification analysis. "
            "In SAP IS-U incidents it is often connected with premise, installation and market communication checks."
        ),
    },
    "EABL": {
        "title": "EABL meter reading results",
        "text": (
            "EABL is used in SAP IS-U meter reading result analysis. It is relevant for validation, "
            "estimated readings, billing input and meter reading document troubleshooting. Related objects "
            "often include EABLG, EL31, EL28, EASTL and device/register data."
        ),
    },
    "EABLG": {
        "title": "EABLG meter reading result details",
        "text": (
            "EABLG is used alongside EABL for meter reading result details and validation context. "
            "It is useful in incidents around implausible readings, missing results or billing simulation discrepancies."
        ),
    },
    "EGERH": {
        "title": "EGERH device history",
        "text": (
            "EGERH contains SAP IS-U device history data. It is commonly checked for device installation, "
            "removal, replacement, register allocation and date interval consistency."
        ),
    },
    "EASTL": {
        "title": "EASTL installation structure allocation",
        "text": (
            "EASTL is relevant for installation structure and device/register allocation analysis. "
            "It is often used with EGERH, EQUI and ETDZ when investigating device or billing-period inconsistencies."
        ),
    },
    "ERCH": {
        "title": "ERCH billing document",
        "text": (
            "ERCH is a central SAP IS-U billing document table. It is useful for billing analysis, "
            "billing simulation, rate determination and troubleshooting of EA00/EA19 outcomes. Related objects "
            "include ERDK for invoicing and EABL/EABLG as meter reading input."
        ),
    },
    "ERDK": {
        "title": "ERDK invoicing document",
        "text": (
            "ERDK is a SAP IS-U invoicing document table. It is reviewed in invoicing, print document, "
            "FI-CA posting and billing-to-invoicing reconciliation incidents."
        ),
    },
    "EDIDS": {
        "title": "EDIDS IDoc status records",
        "text": (
            "EDIDS stores IDoc status records. In SAP IS-U market communication it is important for UTILMD, "
            "MSCONS, APERAK and other IDoc troubleshooting. It is often checked with EDIDC and EDID4."
        ),
    },
    "UTILMD": {
        "title": "UTILMD market communication message",
        "text": (
            "UTILMD is an EDIFACT message used in German market communication for master data and process "
            "exchanges. In SAP IS-U incidents it is commonly analyzed through IDoc processing, EDIDS statuses, "
            "APERAK responses and GPKE/WiM process requirements."
        ),
    },
    "MSCONS": {
        "title": "MSCONS meter reading market message",
        "text": (
            "MSCONS is an EDIFACT message used for meter reading and consumption value communication. "
            "SAP IS-U troubleshooting often connects MSCONS to meter reading results, IDoc processing and MaKo validation."
        ),
    },
    "APERAK": {
        "title": "APERAK application acknowledgement",
        "text": (
            "APERAK is an EDIFACT application acknowledgement used to report acceptance or rejection at application level. "
            "In SAP IS-U MaKo incidents, APERAK is often reviewed together with UTILMD/MSCONS payloads and IDoc status records."
        ),
    },
}

PROCESS_KEYWORDS = {
    "meter reading": "meter-reading",
    "billing": "billing",
    "invoicing": "invoicing",
    "device": "device-management",
    "move-in": "move-in-out",
    "move out": "move-in-out",
    "move-out": "move-in-out",
    "fica": "fi-ca",
    "fi-ca": "fi-ca",
    "contract account": "fi-ca",
    "utilmd": "mako",
    "mscons": "mako",
    "aperak": "mako",
    "gpke": "mako",
    "edifact": "edifact",
    "customizing": "customizing",
    "spro": "customizing",
    "message class": "messages",
    "error message": "messages",
    "message number": "messages",
    "idoc status": "messages",
    "function module": "abap",
    "badi": "abap",
    "customer exit": "abap",
    "user exit": "abap",
    "enhancement": "abap",
    "fiori": "fiori",
    "s/4hana": "s4hana",
    "api": "api",
    "country": "country-rules",
    "localization": "country-rules",
    "regulator": "country-rules",
    "cnmc": "country-rules",
    "utility regulator": "country-rules",
    "market registration": "country-rules",
    "supplier switching": "country-rules",
    "change of supplier": "country-rules",
    "market message": "mako",
    "troubleshooting": "troubleshooting",
    "runbook": "troubleshooting",
    "bapi": "abap",
    "odata": "api",
    "cds": "api",
}


DIRECT_TOPIC_URL_RULES = [
    {
        "source_id": "sap-help",
        "markers": ("meter reading", "meter readings", "eabl", "eablg", "el31", "el28", "isu_mr"),
        "urls": (
            "https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/2ac7fe29a0c94cdd88fb80c2cb9f7758/bc90d0533f8e4308e10000000a174cb4.html",
            "https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/021b182b0c47416c8fafed67ebfd78a9/dc277defea7947e9ad3dbe2317adfd0e.html",
            "https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/2ac7fe29a0c94cdd88fb80c2cb9f7758/c590d0533f8e4308e10000000a174cb4.html",
        ),
    },
    {
        "source_id": "sap-help",
        "markers": ("fi-ca", "fica", "contract account", "dfkkop", "fpl9", "dunning", "payment", "clearing"),
        "urls": (
            "https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/0dd6552bb884415f93aaa24c788ae644/b1ffc5536a51204be10000000a174cb4.html",
            "https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/e88ba58a6e71437caa4e67d6bc456a00/8005c5536a51204be10000000a174cb4.html",
            "https://help.sap.com/docs/SAP_S4HANA_CLOUD/cdccca8e03d74101a0135863bc522b49/e63529e1a3fd42e3a0e2c009ac783e0d.html",
        ),
    },
    {
        "source_id": "sap-help",
        "markers": ("move-in", "move out", "move-out", "move-in/out", "ec50e", "final billing", "contract change"),
        "urls": (
            "https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/f4a255a5de524e3992155767996fb1fd/0681ce53118d4308e10000000a174cb4.html",
            "https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/f4a255a5de524e3992155767996fb1fd/8082ce53118d4308e10000000a174cb4.html",
            "https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/e52c8ee6197147ec97dfc2eb8c46a3ad/75b8f8e8301e4d279b0eefaaf244b403.html",
        ),
    },
    {
        "source_id": "sap-help",
        "markers": ("device", "egerh", "eastl", "etdz", "egerr", "installation", "replacement", "register"),
        "urls": (
            "https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/2ac7fe29a0c94cdd88fb80c2cb9f7758/ad90d0533f8e4308e10000000a174cb4.html",
            "https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/2ac7fe29a0c94cdd88fb80c2cb9f7758/6e90d0533f8e4308e10000000a174cb4.html",
            "https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/f4a255a5de524e3992155767996fb1fd/9981ce53118d4308e10000000a174cb4.html",
        ),
    },
    {
        "source_id": "sap-help",
        "markers": ("billing", "invoicing", "erch", "erdk", "ea40", "reversal", "rebill", "rate category", "te420", "te422"),
        "urls": (
            "https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/a003b275c98148ee8a4c3fafe9588fe3/de7bce53118d4308e10000000a174cb4.html",
            "https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/5369e276f6a44dc59cc84eef461146e1/d176691e63fb4cdf8964f54a77a83430.html",
        ),
    },
    {
        "source_id": "sap-help",
        "markers": ("badi", "function module", "bapi", "se37", "enhancement", "abap", "fqevents", "api method"),
        "urls": (
            "https://help.sap.com/docs/SUPPORT_CONTENT/uindustry/3362183791.html",
            "https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/e88ba58a6e71437caa4e67d6bc456a00/8005c5536a51204be10000000a174cb4.html",
            "https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/2a481d567d234d138deea02796134560/cff8125477a98c24e10000000a4450e5.html",
        ),
    },
    {
        "source_id": "sap-help",
        "markers": ("fiori", "s/4hana", "s4hana", "api", "odata", "business role", "catalog", "cds", "embedded analytics"),
        "urls": (
            "https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/021b182b0c47416c8fafed67ebfd78a9/3a739dda36f144ceb151ff0cacb55b48.html",
            "https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/021b182b0c47416c8fafed67ebfd78a9/8fac40d378d84a1e9bfa3daf80c998b0.html",
            "https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/d4eb54ea54944b04923af573b28a1e7d/1e60f14bdc224c2c975c8fa8bcfd7f3f.html",
        ),
    },
    {
        "source_id": "cnmc-spain",
        "markers": ("spain", "spanish", "espaÃ±a", "cnmc", "country market", "autolecturas", "switching"),
        "urls": (
            "https://www.cnmc.es/nuevos-formatos-de-ficheros-de-intercambio-de-informacion-entre-comercializadores-y-distribuidores",
        ),
    },
    {
        "source_id": "uregni-retail",
        "markers": ("united kingdom", "uk", "northern ireland", "utility regulator", "market registration", "change of supplier", "meter configuration"),
        "urls": (
            "https://www.uregni.gov.uk/retail-market-documentation",
            "https://www.uregni.gov.uk/files/uregni/media-files/NI%20Market%20Message%20Implementation%20Guide%20-%20Meter%20Registration%20Baseline%20v3.2.pdf",
            "https://www.uregni.gov.uk/files/uregni/media-files/MP_NI_11_Changes_to_Meter_Configuration_-_v21.pdf",
        ),
    },
    {
        "source_id": "ireland-rmd",
        "markers": ("ireland", "irish", "rmd", "market message", "duos", "emma", "supplier provided reading"),
        "urls": (
            "https://rmdservice.com/market-design/market-messages",
            "https://rmdservice.com/market-design/market-procedures",
        ),
    },
    {
        "source_id": "cre-france",
        "markers": ("france", "french", "cre", "gte", "gtg", "changement fournisseur"),
        "urls": (
            "https://www.cre.fr/gaz/marche-de-detail-du-gaz-naturel/presentation.html",
        ),
    },
]


SAP_HELP_STATIC_SUMMARIES = {
    "bc90d0533f8e4308e10000000a174cb4": (
        "Reading Meters",
        "SAP Help describes periodic and aperiodic meter reading in SAP Utilities. The flow covers meter reading order creation, manual or external upload of readings, validation/correction and transfer of results into Contract Billing. It also references BOR/BAPI access for meter reading documents and results, making it useful for EABL/EABLG, EL28/EL31 and billing-input troubleshooting.",
    ),
    "dc277defea7947e9ad3dbe2317adfd0e": (
        "Managing Meter Readings",
        "SAP Help explains interaction-center meter reading handling for business partners, premises and devices. The documented functions include entering, estimating, validating, releasing implausible readings, viewing history and correcting readings. It points to Utilities Customizing for meter reading data processing and to BAdI ISU_MR_HISTORY_QUERY for controlling the meter reading history window.",
    ),
    "c590d0533f8e4308e10000000a174cb4": (
        "Meter Reading Order",
        "SAP Help describes meter reading orders as register-level documents with planned reading data such as scheduled date and meter reader. Orders can be periodic or aperiodic, including customer readings and move-out scenarios. The topic is relevant for EL28/EL31 checks, order creation, validation and BAPI-based selection of orders/results.",
    ),
    "b1ffc5536a51204be10000000a174cb4": (
        "Contract Accounting Dunning",
        "SAP Help documents FI-CA dunning for overdue receivables, dunning letters and industry-specific dunning actions. In Utilities, budget billing requests and open items can be dunned, dunning runs can create lock documents and dunning proposal postprocessing is possible. This supports FPVA, DFKKOP, locks and contract-account troubleshooting.",
    ),
    "8005c5536a51204be10000000a174cb4": (
        "BAPIs in Contract Accounting",
        "SAP Help lists Contract Accounting BAPIs for contract accounts and FI-CA documents. Covered object methods include finding/existence checks, reading account lists/open items/balances/details, clearing open items, creating/changing contract accounts, posting/reversing documents, resetting clearing and reading last errors. This is valuable for FI-CA integration and ABAP/API incident analysis.",
    ),
    "e63529e1a3fd42e3a0e2c009ac783e0d": (
        "Clearing Type",
        "SAP Help explains FI-CA clearing types such as manual posting, account maintenance, payment lot and payment run. It links clearing type 06 to BAdI FKK_EVENT_0600 for payment-run grouping criteria. This supports clearing, FP05/FP06/FP04 and payment allocation troubleshooting.",
    ),
    "0681ce53118d4308e10000000a174cb4": (
        "Move-In/Out Processing",
        "SAP Help documents move-in/out processing for premises and business partners. The process uses keys such as business partner, contract account and premise, then executes move-in, move-out or contract change functions. Subsequent processing can reverse billing, invoicing and FI-CA documents when move dates affect already billed periods.",
    ),
    "8082ce53118d4308e10000000a174cb4": (
        "Move-In/Out",
        "SAP Help describes the Utilities move-in/move-out component for creating business partners, contract accounts, contracts and installation allocation, or terminating contracts and triggering final billing/welcome/confirmation activities. It also notes workflow and screen-layout configuration relevance.",
    ),
    "75b8f8e8301e4d279b0eefaaf244b403": (
        "Exact Move-In and Move-Out Time",
        "SAP Help explains requirements where Utilities contracts must consider exact move-in or move-out time instead of only dates, especially for smart-meter time series, TOU and RTP billing. This is relevant for move date/time corrections, billing-period boundaries and contract lifecycle incidents.",
    ),
    "ad90d0533f8e4308e10000000a174cb4": (
        "Device Installation",
        "SAP Help describes technical and billing-related device installation, including allocation to device location or utility installation, register relationships, installation meter readings and Customizing for installation/removal/replacement parameters. It is useful for EGERH/EASTL/ETDZ device setup and billing allocation issues.",
    ),
    "6e90d0533f8e4308e10000000a174cb4": (
        "Device Allocation",
        "SAP Help explains allocation of controlled and controlling devices, including termination/restoration of allocations during technical removal, installation reversal or replacement reversal. This supports device-replacement incidents, allocation validity and register/device-level checks.",
    ),
    "9981ce53118d4308e10000000a174cb4": (
        "Device and Register Info Templates",
        "SAP Help discusses DEVICE_INFO and REGISTER_INFO master data template behavior for device info records, register groups and proposed registers during installation or replacement. It is relevant for register category, meter reading unit and device-info-record consistency issues.",
    ),
    "de7bce53118d4308e10000000a174cb4": (
        "Invoicing Reversal",
        "SAP Help documents invoicing reversal in Utilities, including reversal of FI-CA posting documents, print reversal formatting, budget billing plan handling and the required reversal sequence. It references Customizing for reversal and helps analyze EA15-style invoicing reversals, billing document dependencies and clearing reset behavior.",
    ),
    "d176691e63fb4cdf8964f54a77a83430": (
        "Utilities Product",
        "SAP Help explains Utilities products in S/4HANA and how product characteristics can map to billing artifacts such as rate categories and operands. This is useful for S/4HANA Utilities product-to-billing configuration, rate determination and integration troubleshooting.",
    ),
    "3362183791": (
        "BAdIs for Meter Reading",
        "SAP Help support content lists Utilities meter reading BAdIs and enhancement points, including logic around formal checks, combining EABL records, onsite billing, estimation and meter reading history queries. This supports ABAP enhancement analysis and separation of custom logic from standard meter reading behavior.",
    ),
    "cff8125477a98c24e10000000a4450e5": (
        "Utilities ABAP Integration and Enhancement Reference",
        "SAP Help references Utilities ABAP integration and extensibility points used around service processes, business objects and industry-specific processing. For incident analysis this is a starting point for checking function modules, BAdIs, exits and enhancement implementations together with SE18, SE19, SE37, SE80 and FQEVENTS.",
    ),
    "3a739dda36f144ceb151ff0cacb55b48": (
        "S/4HANA Utilities Roles and Catalogs",
        "SAP Help documents S/4HANA Utilities roles and business catalogs such as Meter Data Specialist, Billing Specialist and Operations Specialist. It also explains that classic SAP GUI backend transactions remain relevant through Fiori Launchpad technical catalogs, supporting role/catalog/Fiori troubleshooting.",
    ),
    "8fac40d378d84a1e9bfa3daf80c998b0": (
        "S/4HANA Utilities Contract Integration",
        "SAP Help describes integration and migration of S/4HANA Utilities contracts and required Utilities Sales Contract Management customizing. It mentions integration activation and process classes for move-out/change scenarios, helping distinguish classic IS-U contracts from S/4HANA integration behavior.",
    ),
    "1e60f14bdc224c2c975c8fa8bcfd7f3f": (
        "APIs on SAP Business Accelerator Hub",
        "SAP Help explains SAP S/4HANA API discovery on SAP Business Accelerator Hub, API types such as OData and SOAP, batch/change-set behavior, authentication methods and metadata/documentation options. This supports S/4HANA Utilities API troubleshooting and integration design.",
    ),
}


@dataclass
class CollectedDocument:
    url: str
    title: str
    text: str


class _ReadableHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self._skip = False
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip = True
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip = False
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        text = " ".join((data or "").split())
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
        elif not self._skip:
            self.text_parts.append(text)

    @property
    def title(self) -> str:
        return " ".join(self.title_parts).strip()

    @property
    def text(self) -> str:
        return "\n".join(self.text_parts).strip()


def fetch_url_document(url: str, timeout: int = 15) -> CollectedDocument:
    """Fetch one public URL and extract a compact text representation."""
    static_summary = _sap_help_static_summary(url)
    if static_summary:
        title, text = static_summary
        return CollectedDocument(url=url, title=title, text=text)

    req = Request(
        url,
        headers={
            "User-Agent": "SapIsuAssistantResearchBot/0.1 (+controlled single-page fetch)"
        },
    )
    with urlopen(req, timeout=timeout) as resp:
        content_type = resp.headers.get("content-type", "")
        is_pdf = "pdf" in content_type.lower() or urlparse(url).path.lower().endswith(".pdf")
        raw = resp.read(MAX_PDF_FETCH_BYTES if is_pdf else MAX_FETCH_CHARS)
    if is_pdf:
        text = _extract_pdf_bytes(raw)
        return CollectedDocument(url=url, title=url.rsplit("/", 1)[-1] or url, text=text[:MAX_RAW_EXCERPT_CHARS])
    if "html" not in content_type.lower():
        text = raw.decode("utf-8", errors="replace")
        return CollectedDocument(url=url, title=url, text=text[:MAX_RAW_EXCERPT_CHARS])
    parser = _ReadableHTMLParser()
    parser.feed(raw.decode("utf-8", errors="replace"))
    if not parser.text.strip():
        summary = _sap_help_static_summary(url)
        if summary:
            title, text = summary
            return CollectedDocument(url=url, title=title, text=text)
    return CollectedDocument(
        url=url,
        title=parser.title or url,
        text=parser.text[:MAX_RAW_EXCERPT_CHARS],
    )


def _extract_pdf_bytes(raw: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(raw))
        pages = []
        for page in reader.pages[:20]:
            page_text = page.extract_text()
            if page_text:
                pages.append(page_text)
            if sum(len(text) for text in pages) >= MAX_RAW_EXCERPT_CHARS:
                break
        text = "\n\n".join(pages).strip()
        if text:
            return text
    except Exception:
        pass
    return raw.decode("utf-8", errors="replace")


def _sap_help_static_summary(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    if not parsed.netloc.lower().endswith("help.sap.com"):
        return None
    for key, summary in SAP_HELP_STATIC_SUMMARIES.items():
        if key in url:
            return summary
    return None


def search_source_urls(topic: str, source: ResearchSource, limit: int = 3, timeout: int = 15) -> list[str]:
    """Search public web results for one source using a conservative site query."""
    if not source.base_url or source.usage_policy == "REFERENCE_ONLY":
        return []
    urls = direct_source_urls_for_topic(topic, source, limit)
    if urls and source.kind in {"OFFICIAL", "TECH_DICTIONARY", "MARKET_RULES", "REGULATOR"}:
        return urls[:limit]
    if len(urls) >= limit:
        return urls[:limit]
    parsed = urlparse(source.base_url)
    domain = parsed.netloc.lower().removeprefix("www.")
    if not domain:
        return urls[:limit]
    query = f"site:{domain} SAP IS-U {topic}"
    search_url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    req = Request(
        search_url,
        headers={
            "User-Agent": "SapIsuAssistantResearchBot/0.1 (+controlled source search)"
        },
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            html = resp.read(MAX_SEARCH_CHARS).decode("utf-8", errors="replace")
    except Exception:
        if urls:
            return urls[:limit]
        raise
    seen = set(urls)
    for href in _extract_hrefs(html):
        normalized = _normalize_search_href(href)
        if not normalized:
            continue
        netloc = urlparse(normalized).netloc.lower().removeprefix("www.")
        if not netloc.endswith(domain):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        urls.append(normalized)
        if len(urls) >= limit:
            break
    return urls


def direct_source_urls_for_topic(topic: str, source: ResearchSource, limit: int) -> list[str]:
    """Build deterministic lookup URLs for object dictionaries before using web search."""
    objects = detect_sap_objects(topic)
    urls: list[str] = []
    topic_urls = _direct_topic_rule_urls(topic, source)
    for url in topic_urls:
        if url not in urls:
            urls.append(url)
        if len(urls) >= limit:
            return urls
    for obj in objects:
        url = _direct_source_url(source, obj)
        if url and url not in urls:
            urls.append(url)
        if len(urls) >= limit:
            break
    return urls


def _direct_topic_rule_urls(topic: str, source: ResearchSource) -> list[str]:
    lower = (topic or "").lower()
    urls: list[str] = []
    for rule in DIRECT_TOPIC_URL_RULES:
        if rule["source_id"] != source.id:
            continue
        if any(marker in lower for marker in rule["markers"]):
            for url in rule["urls"]:
                if url not in urls:
                    urls.append(url)
    return urls


def _direct_source_url(source: ResearchSource, obj: str) -> str | None:
    obj_upper = obj.upper()
    obj_lower = obj_upper.lower()
    if obj_upper in SAP_TABLE_OBJECTS:
        if source.id == "sap-datasheet":
            return f"https://www.sapdatasheet.org/abap/tabl/{obj_lower}.html"
        if source.id == "leanx":
            return f"https://leanx.eu/en/sap/table/{obj_lower}.html"
        if source.id == "tcodesearch":
            return f"https://www.tcodesearch.com/sap-tables/{obj_upper}"
        if source.id == "se80":
            return f"https://www.se80.co.uk/sap-tables/?name={obj_lower}"
    if obj_upper in SAP_TRANSACTION_OBJECTS:
        if source.id == "tcodesearch":
            return f"https://www.tcodesearch.com/sap-tcodes/{obj_upper}"
        if source.id == "se80":
            return f"https://www.se80.co.uk/sap-tcodes/?name={obj_lower}"
    if obj_upper.startswith(("ISU_", "BAPI_")) or obj_upper in {"BADI", "FQEVENTS"}:
        if source.id == "tcodesearch":
            return f"https://www.tcodesearch.com/sap-fms/{obj_upper}"
        if source.id == "se80":
            return f"https://www.se80.co.uk/sap-function-modules/?name={obj_lower}"
    return None


def seed_documents_for_topic(topic: str, sources: list[ResearchSource], limit: int = 4) -> list[tuple[ResearchSource, CollectedDocument]]:
    """Create safe internal seed documents for known SAP objects when web search finds nothing."""
    definition = find_topic_definition(topic)
    if definition:
        source = _pick_seed_source(list(definition.objects), sources) or _pick_source_by_ids(definition.source_ids, sources)
        if source:
            objects = ", ".join(definition.objects)
            text = (
                f"{definition.seed_text} "
                f"Primary SAP objects for this topic: {objects}. "
                f"Use this as a reviewable starting point and enrich it with official source URLs where available."
            )
            return [
                (
                    source,
                    CollectedDocument(
                        url=_seed_url_for_source(source, definition.objects[0] if definition.objects else definition.id),
                        title=definition.label,
                        text=text,
                    ),
                )
            ]

    upper = (topic or "").upper()
    matches = [obj for obj in SAP_OBJECT_SEEDS if re.search(rf"\b{re.escape(obj)}\b", upper)]
    if not matches:
        return []
    source = _pick_seed_source(matches, sources)
    if not source:
        return []
    documents = []
    for obj in matches[:limit]:
        seed = SAP_OBJECT_SEEDS[obj]
        documents.append(
            (
                source,
                CollectedDocument(
                    url=_seed_url_for_source(source, obj),
                    title=seed["title"],
                    text=seed["text"],
                ),
            )
        )
    return documents


def _pick_source_by_ids(source_ids: Iterable[str], sources: list[ResearchSource]) -> ResearchSource | None:
    for source_id in source_ids:
        for source in sources:
            if source.id == source_id:
                return source
    return None


def _pick_seed_source(objects: list[str], sources: list[ResearchSource]) -> ResearchSource | None:
    market_objects = {"UTILMD", "MSCONS", "APERAK", "INVOIC", "REMADV", "CONTRL", "GPKE", "WIM", "MABIS"}
    if any(obj in market_objects for obj in objects):
        for source in sources:
            if source.kind == "MARKET_RULES":
                return source
    if any(obj in SAP_TRANSACTION_OBJECTS for obj in objects):
        preferred = ["tcodesearch", "se80", "sap-help", "sap-datasheet", "leanx"]
    elif any(obj in {"SE37", "SE80", "SE18", "SE19", "SE24", "BADI", "FQEVENTS"} for obj in objects):
        preferred = ["se80", "sap-datasheet", "tcodesearch", "sap-help"]
    elif any(obj in {"API", "S4HANA", "FIORI"} for obj in objects):
        preferred = ["sap-business-accelerator-hub", "sap-help", "sap-learning", "sap-community-utilities"]
    else:
        preferred = ["sap-datasheet", "leanx", "tcodesearch", "se80", "sap-help"]
    for source_id in preferred:
        for source in sources:
            if source.id == source_id:
                return source
    return sources[0] if sources else None


def _seed_url_for_source(source: ResearchSource, obj: str) -> str:
    upper = obj.upper()
    lower = obj.lower()
    direct = _direct_source_url(source, upper)
    if direct:
        return direct
    if source.id == "sap-datasheet":
        return f"https://www.sapdatasheet.org/abap/tabl/{lower}.html"
    if source.id == "leanx":
        return f"https://leanx.eu/en/sap/table/{lower}.html"
    if source.id == "tcodesearch":
        return f"https://www.tcodesearch.com/sap-tables/{obj}"
    if source.id == "se80":
        return f"https://www.se80.co.uk/sap-tables/?name={lower}"
    if source.id == "bdew-edi-energy":
        return "https://www.edi-energy.de"
    return source.base_url or f"sap-object://{obj}"


def _extract_hrefs(html: str) -> list[str]:
    return re.findall(r'href=["\']([^"\']+)["\']', html or "", flags=re.IGNORECASE)


def _normalize_search_href(href: str) -> str | None:
    href = href.replace("&amp;", "&")
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        href = unquote(target)
        parsed = urlparse(href)
    if parsed.scheme not in {"http", "https"}:
        return None
    return href.split("#", 1)[0]


def normalize_candidate(
    *,
    source: ResearchSource,
    title: str,
    raw_excerpt: str,
    url: str | None = None,
) -> dict:
    """Normalize collected content into a KB candidate without approving it."""
    title = (title or url or "SAP IS-U research candidate").strip()
    raw_excerpt = _compact(raw_excerpt)
    combined = f"{title}\n{raw_excerpt}"
    sap_objects = detect_sap_objects(combined)
    tags = infer_tags(combined, source)
    kb_type = infer_kb_type(combined, source)
    process = infer_process(combined)
    country = infer_country(combined, tags)
    confidence = infer_confidence(source, raw_excerpt, sap_objects)
    copyright_risk = infer_copyright_risk(source, raw_excerpt)
    audit_status, audit_notes = audit_candidate(source, raw_excerpt, sap_objects, copyright_risk)

    content = build_markdown(
        title=title,
        raw_excerpt=raw_excerpt,
        source=source,
        url=url,
        sap_objects=sap_objects,
        tags=tags,
        process=process,
        copyright_risk=copyright_risk,
    )

    return {
        "title": title,
        "raw_excerpt": raw_excerpt,
        "kb_type": kb_type,
        "content_markdown": content,
        "tags": tags,
        "sap_objects": sap_objects,
        "signals": {
            "module": "SAP IS-U",
            "process": process,
            "country": country,
            "sap_area": infer_sap_area(tags, sap_objects),
            "source_tier": source.tier,
            "source_kind": source.kind,
        },
        "sources": {
            "source_id": source.id,
            "source_name": source.name,
            "source_tier": source.tier,
            "source_kind": source.kind,
            "usage_policy": source.usage_policy,
            "url": url,
            "confidence_score": confidence,
            "copyright_risk": copyright_risk,
        },
        "confidence_score": confidence,
        "copyright_risk": copyright_risk,
        "audit_status": audit_status,
        "audit_notes": audit_notes,
    }


def detect_sap_objects(text: str) -> list[str]:
    upper = text.upper()
    found = {obj for obj in KNOWN_SAP_OBJECTS if re.search(rf"\b{re.escape(obj)}\b", upper)}
    for token in re.findall(r"\b[A-Z][A-Z0-9_/-]{3,30}\b", upper):
        if token.startswith(("SAP", "ISU", "FKK", "DFKK", "EUI", "EDI")) or token in KNOWN_SAP_OBJECTS:
            found.add(token.strip("/-"))
    return sorted(found)


def infer_tags(text: str, source: ResearchSource) -> list[str]:
    lower = text.lower()
    tags = {"sap-isu"}
    if source.kind == "MARKET_RULES":
        tags.add("mako")
    if source.kind == "REGULATOR":
        tags.add("country-rules")
    if source.kind == "TECH_DICTIONARY":
        tags.add("technical-object")
    for keyword, tag in PROCESS_KEYWORDS.items():
        if keyword in lower:
            tags.add(tag)
    for token in ["utilmd", "mscons", "aperak", "idoc", "edifact", "gpke", "wim", "mabis"]:
        if token in lower:
            tags.add(token)
    return sorted(tags)


def infer_kb_type(text: str, source: ResearchSource) -> str:
    lower = text.lower()
    if any(k in lower for k in ["customizing", "spro", "configuration table", "sm30"]):
        return "CUSTOMIZING"
    if (
        any(k in lower for k in ["message class", "error message", "message number", "status 51", "status 64"])
        or ("idoc status" in lower and source.kind != "MARKET_RULES")
    ):
        return "SAP_MESSAGE"
    if any(k in lower for k in ["badi", "function module", "customer exit", "user exit", "enhancement spot", "fqevents", "class ", "method "]):
        return "ABAP_TECH_NOTE"
    if any(k in lower for k in ["runbook", "troubleshooting", "end-to-end", "root cause triage"]):
        return "RUNBOOK"
    if any(k in lower for k in ["country-specific", "country market", "local regulator", "localization"]):
        return "MARKET_PROCESS"
    if source.kind == "REGULATOR":
        return "MARKET_PROCESS"
    if source.kind == "MARKET_RULES" or any(k in lower for k in ["utilmd", "mscons", "aperak", "gpke", "mabis", "wim"]):
        return "EDIFACT_SPEC" if "edifact" in lower or source.kind == "MARKET_RULES" else "MARKET_PROCESS"
    if any(re.search(rf"\b{re.escape(obj)}\b", text.upper()) for obj in SAP_TABLE_OBJECTS):
        return "SAP_TABLE"
    if any(k in lower for k in ["transaction", "tcode", "t-code"]):
        return "SAP_TRANSACTION"
    if any(k in lower for k in ["table", "field", "data element", "domain"]):
        return "SAP_TABLE"
    if any(k in lower for k in ["program", "report"]):
        return "SAP_PROGRAM"
    if "api" in lower or source.id == "sap-business-accelerator-hub":
        return "SAP_API"
    if any(k in lower for k in ["error", "issue", "incident", "problem"]):
        return "INCIDENT_PATTERN"
    if source.kind == "TECH_DICTIONARY":
        return "TECHNICAL_OBJECT"
    return "SAP_PROCESS"


def infer_process(text: str) -> str | None:
    lower = text.lower()
    for keyword, process in PROCESS_KEYWORDS.items():
        if keyword in lower:
            return process
    return None


def infer_country(text: str, tags: Iterable[str]) -> str | None:
    lower = (text or "").lower()
    country_markers = {
        "northern ireland": "GB-NIR",
        "utility regulator": "GB-NIR",
        "rmdservice": "IE",
        "ireland": "IE",
        "irish": "IE",
        "cnmc": "ES",
        "spain": "ES",
        "spanish": "ES",
        "cre france": "FR",
        "cre.fr": "FR",
        "france": "FR",
        "french": "FR",
        "netherlands": "NL",
        "united kingdom": "GB",
        "great britain": "GB",
        "italy": "IT",
        "austria": "AT",
        "switzerland": "CH",
        "belgium": "BE",
        "nordic": "NORDICS",
        "poland": "PL",
        "czech": "CZ",
        "portugal": "PT",
        "germany": "DE",
        "german": "DE",
        "bdew": "DE",
        "edi@energy": "DE",
    }
    for marker, code in country_markers.items():
        if marker in lower:
            return code
    tag_set = set(tags)
    if tag_set & {"mako", "gpke", "edifact", "utilmd", "mscons", "aperak"} and "country-rules" not in tag_set:
        return "DE"
    return None


def infer_sap_area(tags: Iterable[str], sap_objects: Iterable[str]) -> str | None:
    tag_set = set(tags)
    obj_set = set(sap_objects)
    if tag_set & {"customizing"} or obj_set & {"SPRO", "SM30"}:
        return "IS-U Customizing"
    if tag_set & {"messages"}:
        return "SAP Messages / Errors"
    if tag_set & {"abap"} or obj_set & {"SE37", "SE80", "SE18", "SE19", "SE24", "BADI", "FQEVENTS"}:
        return "ABAP / Enhancements"
    if tag_set & {"country-rules"}:
        return "Country Market Rules"
    if tag_set & {"fiori", "s4hana", "api"}:
        return "S/4HANA Utilities"
    if tag_set & {"troubleshooting"}:
        return "IS-U Troubleshooting"
    if tag_set & {"mako", "edifact", "utilmd", "mscons", "aperak", "gpke"}:
        return "IS-U IDE"
    if tag_set & {"billing", "invoicing"} or obj_set & {"ERCH", "ERDK", "EA00", "EA19"}:
        return "IS-U Billing/Invoicing"
    if tag_set & {"meter-reading"} or obj_set & {"EABL", "EABLG", "EL31", "EL28"}:
        return "IS-U Meter Reading"
    if tag_set & {"device-management"} or obj_set & {"EQUI", "EGERH", "ETDZ", "EASTL"}:
        return "IS-U Device Management"
    if tag_set & {"fi-ca"} or obj_set & {"FKKVKP", "DFKKOP", "FPL9", "FP03"}:
        return "FI-CA"
    return "SAP IS-U"


def infer_confidence(source: ResearchSource, raw_excerpt: str, sap_objects: list[str]) -> float:
    score = TIER_CONFIDENCE.get(source.tier, 0.4)
    if sap_objects:
        score += 0.05
    if len(raw_excerpt) < 120:
        score -= 0.15
    return max(0.05, min(score, 0.98))


def infer_copyright_risk(source: ResearchSource, raw_excerpt: str) -> str:
    if source.usage_policy == "REFERENCE_ONLY":
        return "HIGH"
    if source.usage_policy == "CONTEXT_ONLY":
        return "MEDIUM"
    if len(raw_excerpt) > 8_000:
        return "MEDIUM"
    return "LOW"


def audit_candidate(
    source: ResearchSource,
    raw_excerpt: str,
    sap_objects: list[str],
    copyright_risk: str,
) -> tuple[str, str]:
    notes = []
    lower = (raw_excerpt or "").lower()
    has_official_process_signal = (
        source.tier == "A"
        and source.usage_policy == "SUMMARY_OK"
        and copyright_risk == "LOW"
        and (
            source.kind in {"OFFICIAL", "MARKET_RULES", "REGULATOR"}
            or "sap utilities" in lower
            or "sap is-u" in lower
            or any(marker in lower for marker in PROCESS_KEYWORDS)
        )
    )
    if copyright_risk == "HIGH":
        notes.append("High copyright risk; keep as reference metadata only.")
    if source.tier in {"C", "D"}:
        notes.append("Secondary/context source; validate against an official or technical source.")
    if not sap_objects and not has_official_process_signal:
        notes.append("No SAP object was detected automatically.")
    if len(raw_excerpt) < 80:
        notes.append("Excerpt is short; candidate may be too weak.")
    if copyright_risk == "HIGH":
        return "REJECTED", " ".join(notes)
    if notes:
        return "NEEDS_REVIEW", " ".join(notes)
    return "PASSED", "Automatic audit passed; can be auto-indexed when auto-index is enabled."


def build_markdown(
    *,
    title: str,
    raw_excerpt: str,
    source: ResearchSource,
    url: str | None,
    sap_objects: list[str],
    tags: list[str],
    process: str | None,
    copyright_risk: str,
) -> str:
    source_line = f"{source.name}" + (f" ({url})" if url else "")
    objects = ", ".join(sap_objects) if sap_objects else "None detected"
    tag_text = ", ".join(tags) if tags else "sap-isu"
    summary = summarize(raw_excerpt)
    return (
        f"# {title}\n\n"
        f"## Summary\n{summary}\n\n"
        f"## SAP IS-U Classification\n"
        f"- Source: {source_line}\n"
        f"- Source tier: {source.tier}\n"
        f"- Process: {process or 'Not determined'}\n"
        f"- Tags: {tag_text}\n"
        f"- SAP objects: {objects}\n"
        f"- Copyright risk: {copyright_risk}\n\n"
        f"## Review Notes\n"
        f"This item was generated as a research candidate and must be reviewed before approval. "
        f"Use the source link for traceability and avoid copying proprietary material verbatim.\n\n"
        f"## Extracted Basis\n{_quote_excerpt(raw_excerpt)}"
    )


def summarize(text: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", _compact(text))
    picked = [s for s in sentences if s][:3]
    return " ".join(picked)[:900] or "No summary available."


def _quote_excerpt(text: str) -> str:
    compact = _compact(text)[:900]
    return "\n".join(f"> {line}" for line in compact.splitlines() if line.strip()) or "> No excerpt available."


def _compact(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [" ".join(line.split()) for line in text.split("\n")]
    compact = "\n".join(line for line in lines if line)
    return compact[:MAX_RAW_EXCERPT_CHARS]

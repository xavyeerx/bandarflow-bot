"""
scraper/universe.py — Universe saham IDX berdasarkan likuiditas.

Difilter ke 257 saham terliquid (avg nilai transaksi harian >= ~1.8B).
Diurutkan dari terliquid ke non-liquid berdasarkan data 20 hari terakhir.
Sumber: docs/LIQUIDITY_RANKING.md
"""

import logging
from typing import List

logger = logging.getLogger(__name__)

# 257 saham terliquid IDX, diurutkan dari terliquid ke non-liquid
# Sumber: docs/LIQUIDITY_RANKING.md (avg nilai transaksi harian 20 hari terakhir)
_FULL_UNIVERSE = [
    "TPIA", "DSSA", "AMMN", "BUMI", "TLKM", "ANTM", "BRPT",
    "ASII", "CUAN", "BREN", "PTRO", "BRMS", "DEWA", "AMRT", "MDKA", "EMAS",
    "TINS", "BUVA", "AADI", "BIPI", "RAJA", "INCO", "ADRO", "MAPI", "BNBR",
    "BULL", "MBMA", "ENRG", "MEDC", "INDF", "KLBF", "ITMG", "NCKL", "ESSA", "WIFI",
    "PGAS", "MINA", "INKP", "CDIA", "ADMR", "CPIN", "PTBA", "PSAB", "ARCI", "JPFA",
    "ASPR", "INDY", "SUPA", "PACK", "ISAT", "IMPC", "TKIM", "TOWR",
    "MSIN", "UNVR", "RATU", "RMKE", "PANI", "BUKA", "AKRA", "BRIS", "SMGR", "EMTK",
    "INET", "VKTR", "TAPG", "PWON", "SSIA", "KETR", "HRTA", "JSMR", "MIKA", "WBSA",
    "UVCR", "KOTA", "EXCL", "GULA", "JGLE", "BBTN", "GOTO", "AALI", "ARKO", "GGRM",
    "MARK", "PADI", "IRSX", "ESIP", "PGEO", "NZIA", "BDMN", "CYBR", "LSIP",
    "ELSA", "BKSL", "CMNT", "OASA", "HMSP", "BSDE", "CTRA", "MTEL", "BFIN", "SIDO",
    "MYOR", "SSMS", "CMRY", "TRUE", "MAPA", "MPMX", "AYAM", "PNLF", "CBDK", "APIC",
    "DSNG", "CBRE", "PPRE", "HEAL", "GPSO", "SINI", "DEFI", "BAIK", "ACES", "SCMA",
    "LCKM", "MDIA", "SIMP", "HRUM", "ERAA", "ZATA", "HATM", "NICL", "DATA", "MMIX",
    "KIJA", "BNGA", "FILM", "DEWI", "BSML", "HUMI", "KEEN", "MIDI", "SMRA", "KPIG",
    "ARTO", "NISP", "LEAD", "BWPT", "FORE", "EPAC", "RSCH", "RGAS", "GTSI", "BANK",
    "KUAS", "MBSS", "ASSA", "WMUU", "GRIA", "DKFT", "WEHA", "BJTM", "SRTG", "BSSR",
    "BTPS", "IATA", "MSJA", "COIN", "BBKP", "POWR", "PIPA", "BMTR", "ULTJ", "SMIL",
    "NATO", "NSSS", "AVIA", "VISI", "RLCO", "JARR", "RBMS", "MORA", "BBYB", "COCO",
    "PNBN", "MNCN", "YELO", "TOOL", "TRIN", "SDMU", "SOCI", "TBIG", "PSKT", "MEDS",
    "TOBA", "WIRG", "TOTL", "KJEN", "LPPF", "BELL", "SRSN", "CPRO", "DOOH", "SGER",
    "FORU", "DGWG", "CTTH", "WIIM", "NIKL", "KAQI", "PYFA", "DPUM", "LPKR", "STRK",
    "GIAA", "LAJU", "BIRD", "ELTY", "BJBR", "GPRA", "JATI", "KOCI", "NEST", "GMFI",
    "DFAM", "MGRO", "SMDR", "PADA", "UDNG", "RALS", "NRCA", "BEEF", "BDKR", "FUTR",
    "KRYA", "APLN", "ALII", "PRDA", "MSKY", "CFIN", "OILS", "CLEO", "NTBK", "ASHA",
    "RMKO", "ICON", "DAAZ", "GZCO", "TMPO", "AHAP", "NETV",
]


def get_stock_universe() -> List[str]:
    """
    Return 257 saham terliquid IDX, diurutkan dari terliquid ke non-liquid.
    """
    codes = list(dict.fromkeys(_FULL_UNIVERSE))  # dedup preserve order
    logger.info("Total universe: %d emiten (liquid universe)", len(codes))
    return codes

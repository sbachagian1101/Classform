from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


MONTHS = {m: i for i, m in enumerate(['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'], 1)}


@dataclass
class PastRace:
    finish_raw: str = ''
    finish_pos: Optional[int] = None
    finish_status: str = ''
    margin: Optional[float] = None
    field_size: Optional[int] = None
    date_raw: str = ''
    date: Optional[datetime] = None
    track: str = ''
    race_desc: str = ''
    class_no: Optional[int] = None
    level_label: str = ''
    discipline: str = 'FLAT'
    is_handicap: bool = False
    is_claiming: bool = False
    prize_raw: str = ''
    prize_eur: Optional[float] = None  # legacy alias for prize_amount
    prize_amount: Optional[float] = None
    prize_currency: str = ''
    country: str = ''
    benchmark_rating: Optional[int] = None
    grade_label: str = ''
    distance_m: Optional[int] = None
    surface: str = ''
    going: str = ''
    raw: str = ''


@dataclass
class Runner:
    number: int
    horse: str
    odds: Optional[float] = None
    form: str = ''
    age_sex: str = ''
    weight: Optional[float] = None
    barrier: Optional[int] = None
    jockey: str = ''
    trainer: str = ''
    past_races: list[PastRace] = field(default_factory=list)
    scratched: bool = False
    raw: str = ''


@dataclass
class Race:
    race_no: Optional[int] = None
    time: str = ''
    name: str = ''
    age: str = ''
    weight_condition: str = ''
    race_type: str = ''
    current_class: Optional[int] = None
    discipline: str = 'FLAT'
    is_handicap: bool = False
    is_claiming: bool = False
    prize_raw: str = ''
    prize_eur: Optional[float] = None  # legacy alias for prize_amount
    prize_amount: Optional[float] = None
    prize_currency: str = ''
    country: str = ''
    benchmark_rating: Optional[int] = None
    grade_label: str = ''
    distance_m: Optional[int] = None
    surface: str = ''
    going: str = ''
    runners: list[Runner] = field(default_factory=list)
    source_text: str = ''


def _clean_md(text: str) -> str:
    text = text.replace('\u00a0', ' ').replace('\u202f', ' ')
    # preserve link labels only
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = text.replace('**', '').replace('######', '').replace('#####', '').replace('####', '').replace('###', '').replace('##', '')
    text = text.replace('\\:', ':')
    return text


def _clean_cell(cell: str) -> str:
    cell = _clean_md(cell)
    cell = re.sub(r'\s+', ' ', cell).strip(' |\t')
    return cell.strip()


def _parse_money(raw: str) -> Optional[float]:
    if not raw:
        return None
    s = raw.replace(',', '').replace('€', '').replace('$', '').replace('£', '').strip()
    mult = 1.0
    if re.search(r'k\b', s, re.I):
        mult = 1000.0
        s = re.sub(r'k\b', '', s, flags=re.I)
    m = re.search(r'([0-9]+(?:\.[0-9]+)?)', s)
    return float(m.group(1)) * mult if m else None


def _parse_currency(raw: str) -> str:
    u = (raw or '').upper()
    if 'EUR' in u or '€' in raw:
        return 'EUR'
    if 'GBP' in u or '£' in raw:
        return 'GBP'
    if 'AUD' in u:
        return 'AUD'
    if 'NZD' in u:
        return 'NZD'
    if 'USD' in u or 'US$' in u:
        return 'USD'
    if 'ZAR' in u or 'R ' in u:
        return 'ZAR'
    return ''


def _detect_country(text: str, currency: str = '') -> str:
    u = (text or '').upper()
    if '/AUSTRALIA/' in u or re.search(r'\bAUSTRALIA\b', u) or currency == 'AUD':
        return 'AUSTRALIA'
    if '/FRANCE/' in u or re.search(r'\bFRANCE\b', u) or currency == 'EUR':
        return 'FRANCE'
    if '/NEW-ZEALAND/' in u or '/NEW_ZEALAND/' in u or currency == 'NZD':
        return 'NEW ZEALAND'
    if '/GREAT-BRITAIN/' in u or '/UNITED-KINGDOM/' in u or currency == 'GBP':
        return 'UNITED KINGDOM'
    return ''


def _parse_benchmark(desc: str) -> tuple[Optional[int], str]:
    """Parse Australian/NZ benchmark labels such as BM62 and BM0-62."""
    u = (desc or '').upper().replace('–', '-').replace('—', '-')
    m = re.search(r'\bBM\s*0\s*-\s*(\d{2,3})\b', u)
    if m:
        n = int(m.group(1))
        return n, f'BM0-{n}'
    m = re.search(r'\bBM\s*(\d{2,3})\b', u)
    if m:
        n = int(m.group(1))
        return n, f'BM{n}'
    return None, ''


def _money_line(line: str) -> bool:
    return bool(re.search(r'\b(?:EUR|AUD|GBP|NZD|USD|ZAR)\b|€|£|\$', line or '', re.I))


def _parse_date(s: str) -> Optional[datetime]:
    try:
        return datetime.strptime(s.strip(), '%d-%b-%Y')
    except Exception:
        return None


def _parse_margin(s: str) -> Optional[float]:
    if not s:
        return None
    if re.search(r'99L', s, re.I):
        return 99.0
    m = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*L', s, re.I)
    return float(m.group(1)) if m else None


def _finish_info(s: str) -> tuple[Optional[int], str]:
    t = _clean_cell(s).upper()
    m = re.search(r'\b(\d{1,2})\s+OF\s+\d+', t)
    if m:
        return int(m.group(1)), ''
    m = re.fullmatch(r'(\d{1,2})', t)
    if m:
        return int(m.group(1)), ''
    for status in ['PU', 'F', 'UR', 'RO', 'BD', 'SU', 'REF', 'DSQ']:
        if re.search(rf'\b{status}\b', t):
            return None, status
    m = re.search(r'\b(\d{1,2})\b', t)
    return (int(m.group(1)), '') if m else (None, t[:12])


def _field_size(s: str) -> Optional[int]:
    t = _clean_cell(s).upper()
    m = re.search(r'\b\d{1,2}\s+OF\s+(\d{1,2})\b', t)
    return int(m.group(1)) if m else None


def _discipline(desc: str) -> str:
    u = desc.upper()
    if 'STPLE' in u or 'STEEPLE' in u or 'CHASE' in u:
        return 'STEEPLE'
    if 'HDLE' in u or 'HURDLE' in u:
        return 'HURDLE'
    return 'FLAT'


def _race_level(desc: str) -> tuple[Optional[int], str]:
    u = desc.upper()
    m = re.search(r'\bCL\s*([1-9])\b', u)
    if m:
        n = int(m.group(1))
        return n, f'CL{n}'
    if re.search(r'\b(?:OPEN\s+)?LR\b|LISTED', u):
        return 0, 'LISTED'
    if re.search(r'\bG\s*1\b|GROUP\s*1|GRADE\s*1', u):
        return -3, 'G1'
    if re.search(r'\bG\s*2\b|GROUP\s*2|GRADE\s*2', u):
        return -2, 'G2'
    if re.search(r'\bG\s*3\b|GROUP\s*3|GRADE\s*3', u):
        return -1, 'G3'
    return None, ''


def _parse_race_header(text: str) -> Race:
    clean = _clean_md(text)
    lines = [_clean_cell(x) for x in clean.splitlines()]
    lines = [x for x in lines if x and not re.fullmatch(r'[:\- |]+', x)]
    race = Race(source_text=text)

    # Race number can be far below the navigation header in full R&S markdown.
    # Prefer the explicit "Form Guide (Race N)" marker, then the standalone number
    # immediately preceding the local race time.
    m_race = re.search(r'Form Guide\s*\(Race\s*(\d{1,2})\)', clean, re.I)
    if m_race:
        race.race_no = int(m_race.group(1))
    time_idx = None
    for i, line in enumerate(lines):
        if not race.time and re.fullmatch(r'\d{1,2}:\d{2}', line):
            race.time = line
            time_idx = i
            break
    if race.race_no is None and time_idx is not None:
        for line in reversed(lines[max(0, time_idx-8):time_idx]):
            if re.fullmatch(r'\d{1,2}', line):
                n = int(line)
                if 1 <= n <= 30:
                    race.race_no = n
                    break

    # name: usually the line preceding Age:
    for i, line in enumerate(lines):
        if line.startswith('Age:'):
            if i > 0:
                race.name = lines[i-1].lstrip('# ').strip()
            hdr = line
            ma = re.search(r'Age:\s*(.*?)\s+WT:', hdr, re.I)
            if ma:
                race.age = ma.group(1).strip()
            mw = re.search(r'WT:\s*(.*?)\s+Type:', hdr, re.I)
            if mw:
                race.weight_condition = mw.group(1).strip()
            mt = re.search(r'Type:\s*(.*?)(?:\s+Fastest Time:|$)', hdr, re.I)
            if mt:
                race.race_type = mt.group(1).strip()
            break

    race.country = _detect_country(text)
    race.benchmark_rating, race.grade_label = _parse_benchmark(race.race_type)
    # In Australia, CL1/CL2/CL3 are restricted win classes and must NOT be
    # interpreted as the French CL1 > CL2 > CL3 hierarchy. Group/Listed labels
    # remain universal and are still parsed by _race_level.
    parsed_class, parsed_label = _race_level(race.race_type)
    if race.country == 'AUSTRALIA':
        if parsed_class is not None and parsed_class <= 0:
            race.current_class, race.grade_label = parsed_class, parsed_label
        else:
            race.current_class = None
            if not race.grade_label:
                m_au = re.search(r'\bCL\s*([1-9])\b|\bCLASS\s*([1-9])\b', race.race_type, re.I)
                if m_au:
                    n = int(m_au.group(1) or m_au.group(2))
                    race.grade_label = f'CL{n}'
                elif re.search(r'\bMDN\b|MAIDEN', race.race_type, re.I):
                    race.grade_label = 'MDN'
                elif re.search(r'\bOPEN\b', race.race_type, re.I):
                    race.grade_label = 'OPEN'
    else:
        race.current_class, race.grade_label = parsed_class, parsed_label
    race.discipline = _discipline(race.race_type)
    race.is_handicap = ('HCP' in race.race_type.upper() or race.benchmark_rating is not None
                        or bool(re.search(r'\bHANDICAP\b', race.name, re.I)))
    race.is_claiming = bool(re.search(r'\bCLM\b|CLAIM', race.race_type.upper()))

    # Prize immediately after header, then distance/surface/going.
    age_idx = next((i for i, x in enumerate(lines) if x.startswith('Age:')), -1)
    scan = lines[age_idx + 1: age_idx + 12] if age_idx >= 0 else lines[:30]
    for line in scan:
        if not race.prize_raw and _money_line(line):
            race.prize_raw = line
            race.prize_amount = _parse_money(line)
            race.prize_eur = race.prize_amount  # backward compatibility
            race.prize_currency = _parse_currency(line)
            if not race.country:
                race.country = _detect_country(text, race.prize_currency)
            continue
        m = re.search(r'\b(\d{3,5})m\b(?:\s+([A-Z ]+?))?(?:\s+(GOOD|SOFT|HEAVY|GOOD TO SOFT|GOOD-SOFT|GS|S|SH|G|N|SL))?$', line, re.I)
        if m:
            race.distance_m = int(m.group(1))
            rest = line[m.end(1):].strip().upper()
            if 'ALL WEATHER' in rest or re.search(r'\bAW\b', rest):
                race.surface = 'ALL WEATHER'
            elif 'TURF' in rest:
                race.surface = 'TURF'
            # last token(s) as going
            for g in ['GOOD TO SOFT','GOOD-SOFT','HEAVY','SOFT','GOOD','SH','GS','SL','N','S','G']:
                if rest.endswith(g):
                    race.going = g
                    break
            break
    return race


def _runner_starts(text: str) -> list[tuple[int, int]]:
    # Markdown exported by R&S uses **N** for the runner number. Prefer that exact
    # marker because ordinary integers inside a runner section are weights/barriers.
    raw_lines = text.replace('\u00a0', ' ').replace('\u202f', ' ').splitlines()
    bold = []
    start_idx = 0
    for i, l in enumerate(raw_lines):
        if 'Bookmaker' in l or 'Best Odds Fluc' in l:
            start_idx = i
    for i in range(start_idx, len(raw_lines)):
        m = re.fullmatch(r'\s*\*\*(\d{1,2})\*\*\s*', raw_lines[i])
        if m and 1 <= int(m.group(1)) <= 30:
            bold.append((i, int(m.group(1))))
    if len(bold) >= 2:
        return bold

    # Plain copied page text has no markdown marker. Detect the R&S runner header
    # pattern: runner number -> compact form code -> horse name -> age/sex, or for
    # debutants/no-form runners: runner number -> horse name -> age/sex.
    clean = _clean_md(text)
    lines = clean.splitlines()
    start_idx = 0
    for i, l in enumerate(lines):
        if 'Bookmaker' in l or 'Best Odds Fluc' in l:
            start_idx = i

    banned = {'TURF','WET','AW','DIST','TRK','CD','FU','SU','LBF','GOOD','SOFT','HEAVY',
              'BOOKMAKER','CHART','JOCKEY','TRAINER','TOP'}

    def meaningful(seq):
        out = []
        for raw in seq:
            x = _clean_cell(raw)
            if not x or re.fullmatch(r'[:\- |]+', x) or re.fullmatch(r'[:\- |]+(?:\|[:\- ]+)+', x):
                continue
            if x.startswith('|') and not re.search(r'[A-Za-z0-9]', x):
                continue
            out.append(x)
        return out

    def horse_like(x: str) -> bool:
        return (len(x) >= 3 and x.upper() == x and re.search(r'[A-Z]', x)
                and x not in banned and not re.match(r'^(?:EUR|AUD|GBP|NZD|USD|ZAR)\b', x)
                and not re.fullmatch(r'[0-9XPFBURD-]+', x))

    candidates = []
    for i in range(start_idx, len(lines)):
        s = _clean_cell(lines[i])
        m = re.fullmatch(r'(\d{1,2})', s)
        if not m:
            continue
        num = int(m.group(1))
        if not 1 <= num <= 30:
            continue
        nxt = meaningful(lines[i+1:i+18])[:10]
        if not nxt:
            continue

        form_idx = next((j for j,x in enumerate(nxt[:3]) if re.fullmatch(r'[0-9xXpPfFuUrRbBdD-]{2,12}', x)), None)
        if form_idx is not None:
            # horse name should follow form fairly quickly, with age/sex later.
            hidx = next((j for j in range(form_idx+1, min(len(nxt), form_idx+5)) if horse_like(nxt[j])), None)
            if hidx is not None:
                candidates.append((i, num))
                continue

        # No-form runner: horse must be the very first meaningful item and age/sex
        # must appear within the next few items. This avoids treating BP numbers as runners.
        if horse_like(nxt[0]) and any(re.fullmatch(r'\d+[FGMHC]', x, re.I) or re.search(r'\d+yo', x, re.I) for x in nxt[1:5]):
            candidates.append((i, num))

    # Keep unique, increasing runner numbers. R&S fields are normally numbered in order.
    out = []
    seen = set()
    last_n = 0
    for i, n in candidates:
        if n in seen:
            continue
        if n < last_n:
            continue
        out.append((i, n)); seen.add(n); last_n = n
    return out

def _parse_runner_section(number: int, section: str) -> Runner:
    clean = _clean_md(section)
    lines = [_clean_cell(x) for x in clean.splitlines()]
    lines = [x for x in lines if x and not re.fullmatch(r'[:\- |]+', x)]

    # Horse from the R&S horse hyperlink when available. Keep country suffixes such
    # as (GB)/(GER) intact.
    m = re.search(r'\[\*\*([^\]]+?)\*\*\]\(https?://www\.racingandsports\.com\.au/thoroughbred/horse/', section, re.I)
    if not m:
        m = re.search(r'\[([^\]]+?)\]\(https?://www\.racingandsports\.com\.au/thoroughbred/horse/', section, re.I)
    horse = _clean_cell(m.group(1)) if m else ''
    if not horse:
        banned = {'TURF','WET','AW','DIST','TRK','CD','FU','SU','LBF','GOOD','SOFT','HEAVY','BOOKMAKER','CHART'}
        # horse is normally within first 12 meaningful lines after number/form
        for x in lines[1:15]:
            xx = x.strip(' |*\t').strip()
            if (len(xx) >= 3 and xx.upper() == xx and re.search(r'[A-Z]', xx)
                    and xx not in banned and not re.fullmatch(r'[0-9XPFBURD]+', xx)
                    and not re.match(r'^(?:EUR|AUD|GBP|NZD|USD|ZAR)\b', xx)):
                horse = xx
                break
    horse = horse or f'Runner {number}'

    # form: first compact form code after number
    form = ''
    for x in lines[1:8]:
        if re.fullmatch(r'[0-9xXpPfFuUrRbBdD-]{2,12}', x):
            form = x
            break

    prehist = clean
    cut = re.search(r'\bCareer\b|\bFP\s*Marg\s*Date\b|\bFPMargDate', prehist, re.I)
    if cut:
        prehist = prehist[:cut.start()]
    mo = re.search(r'\$\s*([0-9]+(?:\.[0-9]+)?)', prehist)
    odds = float(mo.group(1)) if mo else None

    age_sex = ''
    ma = re.search(r'\b(\d+yo\s+[A-Z]{1,3}(?:\s+(?:Gelding|Mare|Filly|Horse|Colt))?)\b', clean, re.I)
    if ma:
        age_sex = ma.group(1)
    elif re.search(r'\b\d+[FGMHC]\b', clean):
        age_sex = re.search(r'\b\d+[FGMHC]\b', clean).group(0)

    # Weight/barrier from early lines - use age marker then first number(s), but optional.
    weight = None; barrier = None
    # R&S plain paste: age-sex, weight, BP appear sequentially early.
    idx_age = next((i for i, x in enumerate(lines[:35]) if re.fullmatch(r'\d+[FGMHC]', x) or 'yo' in x.lower()), None)
    if idx_age is not None:
        nums = []
        for x in lines[idx_age+1:idx_age+10]:
            if re.fullmatch(r'\d+(?:\.\d+)?', x):
                nums.append(x)
            if len(nums) >= 2:
                break
        if nums:
            weight = float(nums[0])
        if len(nums) > 1:
            barrier = int(float(nums[1]))

    past_races = _parse_past_races(section)
    scratched = bool(re.search(r'\bSCRATCHED\b|NON\s+PARTANT', clean, re.I))
    return Runner(number=number, horse=horse, odds=odds, form=form, age_sex=age_sex,
                  weight=weight, barrier=barrier, past_races=past_races, scratched=scratched, raw=section)


def _parse_past_races(section: str) -> list[PastRace]:
    clean = _clean_md(section)
    races: list[PastRace] = []
    for raw_line in clean.splitlines():
        if not re.search(r'\b\d{2}-[A-Za-z]{3}-\d{4}\b', raw_line):
            continue
        if re.search(r'FPMargDate|FP\s+Marg\s+Date', raw_line, re.I):
            continue
        line = _clean_cell(raw_line)
        if not line:
            continue

        # Markdown/table lines can be split reliably by pipes.
        cells = [_clean_cell(c) for c in raw_line.split('|')]
        cells = [c for c in cells if c]
        date_i = next((i for i,c in enumerate(cells) if re.fullmatch(r'\d{2}-[A-Za-z]{3}-\d{4}', c)), None)
        if date_i is not None and date_i >= 2:
            fp = cells[0]
            margin = cells[1] if len(cells) > 1 else ''
            date_raw = cells[date_i]
            track = cells[date_i+1] if len(cells) > date_i+1 else ''
            race_desc = cells[date_i+2] if len(cells) > date_i+2 else ''
            prize = cells[date_i+3] if len(cells) > date_i+3 else ''
            dist = cells[date_i+4] if len(cells) > date_i+4 else ''
            sot = cells[date_i+5] if len(cells) > date_i+5 else ''
        else:
            # Plain-text paste: use date and currency/distance anchors.
            dm = re.search(r'\b(\d{2}-[A-Za-z]{3}-\d{4})\b', line)
            if not dm:
                continue
            date_raw = dm.group(1)
            pre = line[:dm.start()].strip()
            post = line[dm.end():].strip()
            # finish + margin from text before date
            mm = re.search(r'(99L|\d+(?:\.\d+)?L)\s*$', pre, re.I)
            margin = mm.group(1) if mm else ''
            fp = pre[:mm.start()].strip() if mm else pre
            # track is first token after date
            tm = re.match(r'([^\s]+)\s+(.*)', post)
            if not tm:
                continue
            track, rest = tm.group(1), tm.group(2)
            money_m = re.search(r'((?:EUR\s*€?|AUD\s*\$|GBP\s*£?|NZD\s*\$|USD\s*\$|ZAR\s*R?)\s*[0-9,.]+(?:\.[0-9]+)?k?|[€£$]\s*[0-9,.]+(?:\.[0-9]+)?k?)', rest, re.I)
            if money_m:
                race_desc = rest[:money_m.start()].strip()
                prize = money_m.group(1)
                after_money = rest[money_m.end():].strip()
            else:
                # fallback: class/race desc until distance
                race_desc = rest
                prize = ''
                after_money = rest
            dist_m = re.search(r'\b(\d{3,5}m)\b', after_money, re.I)
            dist = dist_m.group(1) if dist_m else ''
            sot = after_money[dist_m.end():].strip() if dist_m else ''

        pos, status = _finish_info(fp)
        prize_currency = _parse_currency(prize)
        country = _detect_country('', prize_currency)
        benchmark_rating, benchmark_label = _parse_benchmark(race_desc)
        class_no, level_label = _race_level(race_desc)
        # Australian CL1/CL2/CL3 are restricted win classes, not the French class hierarchy.
        if country == 'AUSTRALIA':
            if class_no is not None and class_no <= 0:
                pass
            else:
                class_no = None
                if benchmark_label:
                    level_label = benchmark_label
                else:
                    m_au = re.search(r'\bCL\s*([1-9])\b|\bCLASS\s*([1-9])\b', race_desc, re.I)
                    if m_au:
                        level_label = f"CL{int(m_au.group(1) or m_au.group(2))}"
                    elif re.search(r'\bMDN\b|MAIDEN', race_desc, re.I):
                        level_label = 'MDN'
                    elif re.search(r'\bOPEN\b', race_desc, re.I):
                        level_label = 'OPEN'
        disc = _discipline(race_desc)
        dist_m = re.search(r'(\d{3,5})m', dist, re.I)
        surface = ''
        sot_u = sot.upper()
        if re.search(r'\bAW\b', sot_u):
            surface = 'ALL WEATHER'
        elif re.search(r'\bT\b|TURF', sot_u):
            surface = 'TURF'
        going = ''
        for g in ['HEAVY','SOFT','GOOD TO SOFT','SH','GS','SL','GOOD','N','S','G']:
            if re.search(rf'\b{re.escape(g)}\b', sot_u):
                going = g; break

        races.append(PastRace(
            finish_raw=fp, finish_pos=pos, finish_status=status,
            margin=_parse_margin(margin), field_size=_field_size(fp), date_raw=date_raw, date=_parse_date(date_raw),
            track=track, race_desc=race_desc, class_no=class_no, level_label=level_label,
            discipline=disc, is_handicap=('HCP' in race_desc.upper() or benchmark_rating is not None
                                               or bool(re.search(r'\bBM\s*0?\s*-?\s*\d{2,3}\b', race_desc, re.I))),
            is_claiming=bool(re.search(r'\bCLM\b|CLAIM', race_desc.upper())),
            prize_raw=prize, prize_eur=_parse_money(prize), prize_amount=_parse_money(prize),
            prize_currency=prize_currency, country=country, benchmark_rating=benchmark_rating,
            grade_label=level_label or benchmark_label,
            distance_m=int(dist_m.group(1)) if dist_m else None,
            surface=surface, going=going, raw=line
        ))
    # remove duplicate rows caused by malformed markdown repetition
    unique = []
    seen = set()
    for r in races:
        key = (r.date_raw, r.track, r.race_desc, r.finish_raw)
        if key not in seen:
            unique.append(r); seen.add(key)
    return unique


def parse_race(text: str) -> Race:
    race = _parse_race_header(text)
    clean = _clean_md(text)
    lines = clean.splitlines()
    starts = _runner_starts(text)
    if not starts:
        return race
    for idx, (line_i, num) in enumerate(starts):
        end = starts[idx+1][0] if idx+1 < len(starts) else len(lines)
        sec = '\n'.join(lines[line_i:end])
        runner = _parse_runner_section(num, sec)
        if not runner.scratched:
            race.runners.append(runner)
    return race


def race_to_dict(race: Race) -> dict:
    return asdict(race)

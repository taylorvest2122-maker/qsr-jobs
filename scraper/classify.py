"""
Decides whether a posting is a corporate/HQ role, and which function it belongs to.
Edit the word lists below to tune what gets in.
"""
import re

# Titles that mean an in-restaurant (crew / store-level) job -> excluded.
RESTAURANT_TITLES = [
    r"crew", r"team member", r"cashier", r"\bcook\b", r"line cook", r"prep cook", r"dishwasher",
    r"delivery (driver|expert)", r"\bdriver\b(?!.*(manager|director|analyst|engineer))",
    r"barista", r"shift (supervisor|leader|lead|manager)", r"pizza maker", r"customer service rep",
    r"customer service (expeditor|representative)", r"\bcsr\b", r"\bhost(ess)?\b", r"server\b(?!.*(engineer|admin))",
    r"assistant (general |store |restaurant )?manager", r"\bagm\b",
    r"^(restaurant |store )?general manager\b", r"^store manager", r"restaurant manager",
    r"entry level manager", r"manager in training", r"kitchen (manager|leader|team)",
    r"front of house", r"back of house", r"drive[- ]thru", r"hospitality (champion|team)",
    r"carhop", r"sandwich (maker|artist)", r"in-?shop", r"busser", r"bartender", r"team leader\b",
    r"yard driver", r"warehouse associate", r"(cdl|class a) driver",
]
RESTAURANT_RE = re.compile("|".join(RESTAURANT_TITLES), re.I)

# Words that rescue a title even if it matched above (e.g. "Director, Crew Experience").
CORPORATE_HINTS = re.compile(
    r"director|vice president|\bvp\b|analyst|engineer|developer|architect|scientist|counsel|attorney|"
    r"accountant|accounting|finance|marketing|brand manager|product manager|program manager|"
    r"project manager|designer|recruiter|talent|\bhr\b|people|payroll|procurement|supply chain|"
    r"sourcing|strategy|insights|data|software|technology|it |security|legal|tax|treasury|audit|"
    r"communications|culinary|r&d|franchise business|franchise consultant|real estate|construction|"
    r"development manager|operations (consultant|partner|director)|training (manager|director|specialist)|"
    r"specialist|coordinator|administrator|intern|associate,|executive|chief|head of|lead,|principal|"
    r"digital|platform|e-?commerce|loyalty|corporate|support center",
    re.I,
)

# Store numbers like "(05310)" or "#1234" in the title mean a specific restaurant.
STORE_NUMBER_RE = re.compile(r"\(\s*0?\d{3,5}\s*\)|#\s?\d{3,5}\b|\bstore\s?\d{3,5}\b", re.I)

CATEGORIES = [
    ("Technology", r"engineer|developer|software|technology|\bit\b|data|architect|devops|cloud|security|cyber|"
                   r"product owner|scrum|qa\b|quality assurance engineer|digital product|machine learning|\bai\b|pos\b"),
    ("Marketing & Brand", r"marketing|brand|creative|social media|communications|\bpr\b|public relations|media|"
                          r"advertising|loyalty|consumer insights|content|copywriter|art director|digital marketing"),
    ("Finance & Accounting", r"financ|accounting|accountant|tax|treasury|audit|fp&a|controller|payroll|investor"),
    ("People & HR", r"\bhr\b|human resources|people|talent|recruit|compensation|benefits|learning|training|"
                    r"culture|inclusion|hris|workday"),
    ("Supply Chain", r"supply chain|procurement|sourcing|logistics|distribution|purchasing|inventory|category manager"),
    ("Legal & Compliance", r"legal|counsel|attorney|paralegal|compliance|regulatory|privacy|risk"),
    ("Development & Real Estate", r"real estate|construction|design manager|architecture|development|site selection|"
                                  r"facilities|store design|new restaurant"),
    ("Culinary & R&D", r"culinary|chef|menu|food science|r&d|product development|food safety|fsqa|quality assurance"),
    ("Franchise & Field Ops", r"franchise|field|operations consultant|operations partner|business consultant|"
                              r"area director|district|region"),
    ("Strategy & Analytics", r"strategy|analytics|insights|analyst|planning|business intelligence"),
]
CATEGORIES = [(name, re.compile(rx, re.I)) for name, rx in CATEGORIES]


def is_corporate(job, brand_cfg=None):
    title = job.get("title", "")
    brand_cfg = brand_cfg or {}
    if brand_cfg.get("all_corporate"):
        # Source only lists corporate jobs (e.g. a dedicated corporate iCIMS site)
        return not RESTAURANT_RE.search(title) or bool(CORPORATE_HINTS.search(title))
    if STORE_NUMBER_RE.search(title):
        return False
    if RESTAURANT_RE.search(title) and not CORPORATE_HINTS.search(title):
        return False
    dept = (job.get("department") or "").lower()
    if any(w in dept for w in ("restaurant", "hourly", "store", "crew", "in-restaurant")) and not CORPORATE_HINTS.search(title):
        return False
    return True


def categorize(job):
    text = f"{job.get('title', '')} {job.get('department', '')}"
    for name, rx in CATEGORIES:
        if rx.search(job.get("title", "")):
            return name
    for name, rx in CATEGORIES:
        if rx.search(text):
            return name
    return "Other"


def seniority(title):
    t = title.lower()
    if re.search(r"chief|\bc[efmot]o\b|president|\bsvp\b|\bevp\b|\bvp\b|vice president|head of", t):
        return "Executive"
    if re.search(r"director", t):
        return "Director"
    if re.search(r"manager|lead\b|principal|supervisor", t):
        return "Manager"
    if re.search(r"intern|co-?op|apprentice", t):
        return "Intern"
    return "Individual contributor"

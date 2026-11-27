from datetime import date, datetime, timedelta

from .db import (ActivityLog, Challenge, Channel, Equipment, Experiment, Incident, Lab, Material, Message,
                 Notification, PointRule, Quest, Role, Sample, SessionLocal, Space, User, Workstation)
from .services.documents import process_document, store_upload
from .services.gamification import DEFAULT_RULES


def d(days: int) -> date:
    return date.today() + timedelta(days=days)


def iso(*days: int) -> list[str]:
    return [d(x).isoformat() for x in days]


def ago(days: float, hour: int = 10) -> datetime:
    t = datetime.now() - timedelta(days=days)
    return t.replace(hour=hour, minute=(int(days * 37) % 60), second=0, microsecond=0)


HPLC_MANUAL = """# HPLC-04 — instrukcja obsługi

## Uruchomienie
1. Sprawdź poziom rozpuszczalników (faza A: woda + 0,1% kwasu mrówkowego, faza B: acetonitryl).
2. Odpowietrz pompę (purge) przez 5 minut przy 5 mL/min, aby usunąć powietrze z głowicy pompy.
3. Kondycjonuj kolumnę przez 15 minut przy przepływie metody.
4. Przed próbkami wykonaj nastrzyk ślepej próby.

## Wahania ciśnienia — rozwiązywanie problemów
Wahania ciśnienia większe niż ±10 bar zwykle oznaczają powietrze w głowicy pompy lub zatkany filtr liniowy.
Ponownie odpowietrz pompę. Jeśli problem się utrzymuje, wymień filtr liniowy (część 5067-1551) i sprawdź uszczelki.

## Wyłączenie
Przepłucz kolumnę 50% acetonitrylem przez 10 minut, a następnie przechowuj w 100% acetonitrylu.
"""

ACN_SDS = """# Karta charakterystyki — Acetonitryl (CAS 75-05-8)

Zagrożenia: H225 Wysoce łatwopalna ciecz i pary. H302+H312+H332 Działa szkodliwie po połknięciu, w kontakcie ze
skórą lub w następstwie wdychania. H319 Działa drażniąco na oczy.

Przechowywanie: w wentylowanej szafie na substancje łatwopalne, z dala od utleniaczy i źródeł zapłonu.

Pierwsza pomoc: kontakt z oczami — ostrożnie płukać wodą przez co najmniej 15 minut przy oczomyjce.
Kontakt ze skórą — użyj prysznica bezpieczeństwa, zdejmij skażoną odzież.

Wyciek: zapewnij wentylację, usuń źródła zapłonu, zbierz materiałem chłonnym z zestawu do wycieków.
"""


def seed_roles_and_rules(s):
    s.add_all([
        Role(id="manager", name="Kierownik laboratorium", access="admin",
             description="Odpowiada za laboratorium: bezpieczeństwo, budżet, ludzi i konfigurację.",
             responsibilities=["Rozwiązywanie eskalacji", "Konfiguracja punktacji i mapy", "Przegląd raportów ESG i BHP"]),
        Role(id="leader", name="Lider zespołu", access="leader",
             description="Planuje badania i rozdziela pracę.",
             responsibilities=["Tworzenie i przydzielanie questów", "Monitorowanie postępu", "Opieka nad nowymi osobami"]),
        Role(id="engineer", name="Inżynier", access="worker",
             description="Prowadzi metody analityczne i dba o ich jakość.",
             responsibilities=["Obsługa aparatury", "Rozwiązywanie problemów z metodami", "Dzielenie się wiedzą"]),
        Role(id="technician", name="Technik laboratoryjny", access="worker",
             description="Dba o odczynniki, zapasy i przygotowanie stanowisk.",
             responsibilities=["Magazyn i zamówienia", "Przygotowanie stanowisk", "Gospodarka odpadami"]),
        Role(id="service", name="Serwisant", access="worker",
             description="Serwisuje, kalibruje i certyfikuje urządzenia.",
             responsibilities=["Serwisy okresowe", "Kalibracje i certyfikaty", "Naprawy awarii"]),
        Role(id="intern", name="Stażysta", access="worker",
             description="Poznaje laboratorium — przed pierwszym użyciem urządzenia zawsze pyta.",
             responsibilities=["Przestrzeganie SOP", "Proszenie o pomoc", "Questy wiedzy"]),
    ])
    s.add_all([PointRule(id=k, label=label, points=p) for k, label, p in DEFAULT_RULES]
              + [PointRule(id="team_challenge", label="Nagroda za wyzwanie zespołowe", points=50)])


def seed_people_and_labs(s):
    s.add_all([
        User(id="u-anna", name="Dr. Anna Kowalska", initials="AK", role="manager", access="admin",
             skills=["zarządzanie", "bhp", "hplc"], xp=820, lab_id="lab-204", onboarding_done=1, joined=d(-900)),
        User(id="u-ewa", name="Ewa Dąbrowska", initials="ED", role="leader", access="leader",
             skills=["enzymologia", "hplc", "spektrometr"], xp=640, lab_id="lab-204", onboarding_done=1, joined=d(-700)),
        User(id="u-michal", name="Michał Nowak", initials="MN", role="engineer", access="worker",
             skills=["hplc", "krio", "wirówka", "zamrażarka"], xp=510, lab_id="lab-204", onboarding_done=1,
             joined=d(-500)),
        User(id="u-piotr", name="Piotr Wiśniewski", initials="PW", role="service", access="worker",
             skills=["kalibracja", "serwis", "elektronika", "spektrometr", "waga", "autoklaw"], xp=455,
             lab_id="lab-204", onboarding_done=1, joined=d(-1200)),
        User(id="u-kasia", name="Kasia Zielińska", initials="KZ", role="technician", access="worker",
             skills=["magazyn", "odczynniki", "waga", "szafa"], xp=390, lab_id="lab-204", onboarding_done=1,
             joined=d(-400)),
        User(id="u-tomek", name="Tomek Lewandowski", initials="TL", role="intern", access="worker", skills=[],
             xp=40, lab_id="lab-204", mentor_id="u-ewa", onboarding_done=0, joined=d(-3)),
        User(id="u-jan", name="Jan Mazur", initials="JM", role="technician", access="worker",
             skills=["mikrobiologia", "autoklaw", "inkubator", "mikroskop"], xp=300, online=0, lab_id="lab-102",
             onboarding_done=1, joined=d(-600)),
    ])
    s.add_all([
        Lab(id="lab-204", code="LAB-204", name="Laboratorium Biochemii 204", building="Budynek B · Piętro 2",
            manager_id="u-anna", width=20, depth=14, entrance=[10, 13.6],
            points=[
                {"id": "p-exit1", "kind": "exit", "label": "Wyjście główne", "x": 10, "z": 13.8},
                {"id": "p-exit2", "kind": "exit", "label": "Wyjście ewakuacyjne", "x": 19.8, "z": 12.5},
                {"id": "p-eye", "kind": "eyewash", "label": "Oczomyjka", "x": 0.3, "z": 2.8},
                {"id": "p-shower", "kind": "shower", "label": "Prysznic bezpieczeństwa", "x": 0.3, "z": 8.5},
                {"id": "p-aid", "kind": "firstaid", "label": "Apteczka", "x": 19.7, "z": 7.5},
                {"id": "p-ext", "kind": "extinguisher", "label": "Gaśnica CO₂", "x": 12, "z": 0.3},
            ]),
        Lab(id="lab-102", code="LAB-102", name="Laboratorium Mikrobiologii 102", building="Budynek A · Piętro 1",
            manager_id="u-anna", width=16, depth=12, entrance=[8, 11.6],
            points=[
                {"id": "p-exit3", "kind": "exit", "label": "Wyjście główne", "x": 8, "z": 11.8},
                {"id": "p-eye2", "kind": "eyewash", "label": "Oczomyjka", "x": 15.7, "z": 8},
                {"id": "p-aid2", "kind": "firstaid", "label": "Apteczka", "x": 0.3, "z": 4},
            ]),
    ])
    s.flush()
    s.add_all([
        Space(id="z-chem", lab_id="lab-204", name="Strefa zagrożenia chemicznego", kind="zone", x=5.5, z=1.4, w=9, d=2.8,
              hazard="chemiczne"),
        Space(id="z-cryo", lab_id="lab-204", name="Strefa kriogeniczna", kind="zone", x=17.6, z=1.6, w=3.2, d=3.2,
              hazard="kriogeniczne", restricted=1, access_roles=["engineer", "service", "manager", "leader"]),
        Space(id="z-bio", lab_id="lab-102", name="Strefa BSL-2", kind="zone", x=3, z=1.5, w=4, d=3,
              hazard="biologiczne", restricted=1, access_roles=["technician", "manager", "leader"]),
        Workstation(id="WB-1", lab_id="lab-204", name="Stół roboczy WB-1", x=6, z=5.5, w=6, d=1.4, h=0.9,
                    responsible_id="u-ewa"),
        Workstation(id="WB-2", lab_id="lab-204", name="Stół roboczy WB-2", x=14, z=5.5, w=6, d=1.4, h=0.9,
                    responsible_id="u-kasia"),
        Workstation(id="WB-3", lab_id="lab-204", name="Stół roboczy WB-3", x=6, z=10, w=6, d=1.4, h=0.9,
                    responsible_id="u-michal"),
        Workstation(id="WB-4", lab_id="lab-204", name="Stanowisko analityczne 04", x=15, z=10, w=5, d=1.4, h=0.9,
                    responsible_id="u-michal"),
        Workstation(id="WB-5", lab_id="lab-102", name="Stół roboczy WB-5", x=8, z=6, w=8, d=1.4, h=0.9,
                    responsible_id="u-jan"),
    ])


def seed_equipment(s):
    E = Equipment
    s.add_all([
        E(id="FH-01", lab_id="lab-204", name="Dygestorium FH-01", category="Hermetyzacja", kind="hood", status="ok",
          x=3, z=0.7, w=3, d=1.2, h=2.4, serial="FH-2291-A", responsible_id="u-piotr", last_check=d(-20),
          uncertainty="prędkość przepływu ±0,05 m/s", last_service=d(-90), next_service=d(90), cert_expiry=d(150),
          reading="0.52 m/s", manual="Trzymaj szybę poniżej 45 cm. Przed użyciem sprawdź wskaźnik przepływu."),
        E(id="CAB-A", lab_id="lab-204", name="Szafa na kwasy i bufory A", category="Magazyn", kind="storage",
          storage_class="acids", status="ok", x=7, z=0.5, w=2, d=0.8, h=2.0, responsible_id="u-kasia",
          notes="Kwasy i bufory. Dolna półka: zasady."),
        E(id="CAB-F", lab_id="lab-204", name="Szafa na substancje łatwopalne", category="Magazyn", kind="storage",
          storage_class="flammables", status="ok", x=9.5, z=0.5, w=1.4, d=0.8, h=1.4, responsible_id="u-kasia",
          notes="Wentylowana. Tylko rozpuszczalniki. Drzwi samozamykające."),
        E(id="AC-01", lab_id="lab-204", name="Autoklaw AC-01", category="Sterylizacja", kind="instrument",
          status="ok", x=14, z=0.8, w=1.4, d=1.2, h=1.3, serial="AC-77812", responsible_id="u-piotr",
          last_check=d(-7), last_service=d(-60), next_service=d(30), cert_expiry=d(200), reading="121 °C / 15 min",
          manual="Załadunek maks. 2/3. Nigdy nie sterylizuj rozpuszczalników ani szczelnie zamkniętych pojemników."),
        E(id="FRZ-80", lab_id="lab-204", name="Zamrażarka ULT −80 °C", category="Chłodnictwo", kind="freezer",
          storage_class="frozen", status="ok", x=17.6, z=0.8, w=1.3, d=1.1, h=2.0, serial="ULT-80-4411",
          responsible_id="u-michal", last_check=d(-2), uncertainty="±1.5 °C", last_service=d(-150),
          next_service=d(12), cert_expiry=d(4), reading="−79.6 °C",
          manual="Nie trzymaj drzwi otwartych dłużej niż 30 s. Mapa statywów na drzwiach."),
        E(id="INC-02", lab_id="lab-204", name="Inkubator CO₂ INC-02", category="Hodowle komórkowe", kind="instrument",
          status="ok", x=0.8, z=5.2, w=1.0, d=1.2, h=1.8, serial="INC-5521", responsible_id="u-ewa",
          last_check=d(-5), uncertainty="±0.2 °C / ±0.1 % CO₂", last_service=d(-40), next_service=d(140),
          cert_expiry=d(300), reading="37.0 °C · 5.0 % CO₂"),
        E(id="HPLC-04", lab_id="lab-204", workstation_id="WB-1", name="Chromatograf HPLC-04",
          category="Analityka", kind="instrument", status="alert", x=4.2, z=5.5, w=1.4, d=0.8, h=0.8,
          serial="HPLC-1260-0042", responsible_id="u-michal", last_check=d(-1), uncertainty="RT ±0.5 %",
          last_service=d(-12), next_service=d(78), cert_expiry=d(240), reading="Ciśnienie 412 bar (wahania ±18)",
          manual="1. Odpowietrz pompę 5 min. 2. Kondycjonuj kolumnę 15 min. 3. Przed próbkami wykonaj ślepą próbę.",
          notes="Zgłoszono wahania ciśnienia. Podejrzenie powietrza w głowicy pompy."),
        E(id="SP-02", lab_id="lab-204", workstation_id="WB-1", name="Spektrometr UV-Vis SP-02",
          category="Analityka", kind="instrument", status="ok", x=7.6, z=5.5, w=1.0, d=0.7, h=0.5,
          serial="UV-2600-0219", responsible_id="u-piotr", last_check=d(-88), uncertainty="±0.002 Abs",
          last_service=d(-180), next_service=d(3), cert_expiry=d(60), reading="Linia bazowa 0,001 Abs",
          manual="Rozgrzej lampę 20 min. Poniżej 340 nm używaj kuwet kwarcowych."),
        E(id="BAL-01", lab_id="lab-204", workstation_id="WB-2", name="Waga analityczna BAL-01",
          category="Analityka", kind="instrument", status="ok", x=12.3, z=5.5, w=0.6, d=0.6, h=0.4,
          serial="XS205-118", responsible_id="u-kasia", last_check=d(-1), uncertainty="±0.1 mg",
          last_service=d(-30), next_service=d(150), cert_expiry=d(5), reading="Kalibracja wewnętrzna OK"),
        E(id="CF-03", lab_id="lab-204", workstation_id="WB-2", name="Wirówka CF-03", category="Przygotowanie próbek",
          kind="instrument", status="maint", x=15.6, z=5.5, w=0.9, d=0.8, h=0.5, serial="5430R-3391",
          responsible_id="u-piotr", last_check=d(-3), last_service=d(-1), next_service=d(2), cert_expiry=d(180),
          reading="Niewyważenie rotora", notes="Wyłączona do czasu wymiany rotora (zamówiony)."),
        E(id="MIC-01", lab_id="lab-204", workstation_id="WB-3", name="Mikroskop MIC-01", category="Obrazowanie",
          kind="instrument", status="ok", x=4.8, z=10, w=0.7, d=0.7, h=0.7, serial="BX53-221",
          responsible_id="u-ewa", last_check=d(-14), last_service=d(-100), next_service=d(80)),
        E(id="SR-01", lab_id="lab-204", workstation_id="WB-4", name="Statyw na próbki SR-01", category="Magazyn",
          kind="storage", storage_class="general", status="ok", x=16.8, z=10, w=1.0, d=0.6, h=0.35,
          responsible_id="u-michal", notes="Próbki oczekujące na analizę."),
        E(id="BSC-01", lab_id="lab-102", name="Komora laminarna BSC-01", category="Hermetyzacja", kind="hood",
          status="ok", x=3, z=0.7, w=2.2, d=1.1, h=2.3, serial="BSC-II-901", responsible_id="u-jan",
          last_check=d(-10), last_service=d(-120), next_service=d(60), cert_expiry=d(45),
          manual="UV 15 min przed i po pracy. Przecieraj 70% etanolem."),
        E(id="INC-05", lab_id="lab-102", name="Inkubator INC-05", category="Mikrobiologia", kind="instrument",
          status="maint", x=7, z=0.7, w=1.2, d=1.0, h=1.6, responsible_id="u-jan", last_check=d(-30),
          last_service=d(-200), next_service=d(-2), cert_expiry=d(20), reading="36,4 °C (zadane 37)",
          notes="Temperatura dryfuje. Serwis po terminie."),
        E(id="AC-02", lab_id="lab-102", name="Autoklaw AC-02", category="Sterylizacja", kind="instrument",
          status="ok", x=13, z=0.8, w=1.4, d=1.2, h=1.3, responsible_id="u-jan", last_service=d(-20),
          next_service=d(70)),
        E(id="FR-01", lab_id="lab-102", name="Lodówka 4 °C FR-01", category="Chłodnictwo", kind="freezer",
          storage_class="cold", status="ok", x=15.2, z=4, w=1.0, d=1.0, h=1.9, responsible_id="u-jan",
          reading="4.1 °C"),
        E(id="MIC-02", lab_id="lab-102", workstation_id="WB-5", name="Mikroskop MIC-02", category="Obrazowanie",
          kind="instrument", status="ok", x=6, z=6, w=0.7, d=0.7, h=0.7, responsible_id="u-jan"),
        E(id="CNT-01", lab_id="lab-102", workstation_id="WB-5", name="Licznik kolonii CNT-01",
          category="Mikrobiologia", kind="instrument", status="ok", x=10, z=6, w=0.6, d=0.6, h=0.4,
          responsible_id="u-jan"),
        E(id="CAB-B", lab_id="lab-102", name="Szafa na podłoża CAB-B", category="Magazyn", kind="storage",
          storage_class="flammables", status="ok", x=0.6, z=8, w=0.8, d=2, h=2, responsible_id="u-jan"),
    ])


def seed_materials(s):
    M = Material
    s.add_all([
        M(id="MAT-ACN", lab_id="lab-204", name="Acetonitryl (HPLC)", cas="75-05-8", catalog_no="34851-4L",
          lot="SHBN4471", location_id="CAB-F", storage_requirement="flammables", quantity=6.0, unit="L",
          min_stock=2.0, lead_time_days=7, unit_cost_eur=45, delivered=d(-40), expires=d(120),
          hazards=["H225", "H302", "H312", "H319"], responsible_id="u-kasia"),
        M(id="MAT-MEOH", lab_id="lab-204", name="Metanol", cas="67-56-1", catalog_no="M1775-4L", lot="BCCF2210",
          location_id="CAB-F", storage_requirement="flammables", quantity=4.0, unit="L", min_stock=2.0,
          lead_time_days=5, unit_cost_eur=20, delivered=d(-60), expires=d(200),
          hazards=["H225", "H301", "H311", "H370"], responsible_id="u-kasia"),
        M(id="MAT-TRY", lab_id="lab-204", name="Trypsyna (liofilizowana)", cas="9002-07-7", catalog_no="T4799-5G",
          lot="SLCD8812", location_id="FRZ-80", storage_requirement="frozen", quantity=6, unit="fiolki", min_stock=3,
          lead_time_days=10, unit_cost_eur=60, delivered=d(-170), expires=d(3), hazards=["H334"],
          responsible_id="u-ewa"),
        M(id="MAT-PBS", lab_id="lab-204", name="Bufor PBS 10×", cas="—", catalog_no="P5493-1L", lot="RNBK1102",
          location_id="CAB-A", quantity=3.0, unit="L", min_stock=1.0, lead_time_days=3, unit_cost_eur=15,
          delivered=d(-10), expires=d(60), responsible_id="u-kasia"),
        M(id="MAT-NAOH", lab_id="lab-204", name="Wodorotlenek sodu 1 M", cas="1310-73-2", catalog_no="S2770-1L",
          lot="MKCN5512", location_id="CAB-A", quantity=2.0, unit="L", min_stock=0.5, lead_time_days=3,
          unit_cost_eur=10, delivered=d(-100), expires=d(300), hazards=["H314"], responsible_id="u-kasia"),
        M(id="MAT-FA", lab_id="lab-204", name="Kwas mrówkowy", cas="64-18-6", catalog_no="F0507-500ML", lot="STBK3390",
          location_id="CAB-A", storage_requirement="flammables", quantity=0.5, unit="L", min_stock=0.25,
          lead_time_days=5, unit_cost_eur=80, delivered=d(-300), expires=d(12),
          hazards=["H226", "H302", "H314", "H331"], responsible_id="u-kasia"),
        M(id="MAT-PLASMA", lab_id="lab-204", name="Wzorzec kontrolny osocza", cas="—", catalog_no="QC-PL-10",
          lot="QC2026-11", location_id="FRZ-80", storage_requirement="frozen", quantity=10, unit="porcje",
          min_stock=4, lead_time_days=14, unit_cost_eur=30, delivered=d(-15), expires=d(30), sds=0,
          responsible_id="u-michal", notes="Karta SDS nie została jeszcze wgrana."),
        M(id="MAT-AGAR", lab_id="lab-102", name="Agar w proszku", cas="9002-18-0", catalog_no="A1296-500G",
          location_id="CAB-B", quantity=500, unit="g", min_stock=200, lead_time_days=4, unit_cost_eur=0.3,
          expires=d(400), responsible_id="u-jan"),
        M(id="MAT-ETOH", lab_id="lab-102", name="Etanol 70%", cas="64-17-5", catalog_no="E7023-5L",
          location_id="CAB-B", storage_requirement="flammables", quantity=5, unit="L", min_stock=2,
          lead_time_days=3, unit_cost_eur=8, expires=d(90), hazards=["H225", "H319"], responsible_id="u-jan"),
        M(id="MAT-LB", lab_id="lab-102", name="Bulion LB", cas="—", catalog_no="L3022-1L", location_id="FR-01",
          storage_requirement="cold", quantity=2, unit="L", min_stock=1, lead_time_days=4, unit_cost_eur=25,
          expires=d(6), responsible_id="u-jan"),
    ])
    s.add_all([
        Experiment(id="EXP-ENZ", lab_id="lab-204", code="PRJ-204A", title="Kinetyka enzymatyczna", lead_id="u-ewa",
                   members=["u-tomek", "u-kasia"], dates=iso(1, 3, 8, 10, 15),
                   usage=[{"material_id": "MAT-ACN", "amount": 1.0}, {"material_id": "MAT-TRY", "amount": 1},
                          {"material_id": "MAT-PBS", "amount": 0.3}, {"material_id": "MAT-FA", "amount": 0.05}],
                   equipment_ids=["HPLC-04", "SP-02", "WB-1"]),
        Experiment(id="EXP-CRYO", lab_id="lab-204", code="PRJ-204B", title="Krio-test osocza", lead_id="u-michal",
                   members=["u-ewa"], dates=iso(2, 9, 16),
                   usage=[{"material_id": "MAT-PLASMA", "amount": 2}, {"material_id": "MAT-ACN", "amount": 0.5},
                          {"material_id": "MAT-MEOH", "amount": 0.8}],
                   equipment_ids=["FRZ-80", "CF-03", "WB-4"]),
        Experiment(id="EXP-CAL", lab_id="lab-204", code="PRJ-204C", title="Kalibracja kwartalna", lead_id="u-piotr",
                   members=[], dates=iso(5), usage=[{"material_id": "MAT-MEOH", "amount": 0.3}],
                   equipment_ids=["SP-02", "BAL-01"]),
        Experiment(id="EXP-MIC", lab_id="lab-102", code="PRJ-102A", title="Krzywe wzrostu bakterii", lead_id="u-jan",
                   members=[], dates=iso(1, 4, 7),
                   usage=[{"material_id": "MAT-AGAR", "amount": 60}, {"material_id": "MAT-LB", "amount": 0.4},
                          {"material_id": "MAT-ETOH", "amount": 0.5}],
                   equipment_ids=["BSC-01", "INC-05"]),
    ])


def seed_history(s):
    def L(target_type, target_id, user_id, action, note="", at=None, amount=0, data=None, lab="lab-204"):
        return ActivityLog(lab_id=lab, user_id=user_id, target_type=target_type, target_id=target_id, action=action,
                           note=note, amount=amount, data=data or {}, at=at or datetime.now())

    m = "machine"
    s.add_all([
        L(m, "HPLC-04", "u-michal", "issue", "Skoki ciśnienia podczas gradientu", ago(58)),
        L(m, "HPLC-04", "u-piotr", "service", "Wymiana uszczelek pompy, zestaw serwisowy.", ago(12)),
        L(m, "HPLC-04", "u-michal", "fix", "Skoki ciśnienia: odpowietrzono pompę i wymieniono filtr liniowy. Rozwiązane.", ago(30)),
        L(m, "HPLC-04", "u-ewa", "use", "Kinetyka enzymatyczna — seria 3", ago(2, 14)),
        L(m, "HPLC-04", "u-michal", "use", "Przygotowanie krio-testu", ago(1, 9)),
        L(m, "HPLC-04", "u-michal", "issue", "Wahania ciśnienia ±18 bar", ago(1, 11)),
        L(m, "SP-02", "u-piotr", "calibration", "Zweryfikowano dokładność długości fali.", ago(88)),
        L(m, "SP-02", "u-ewa", "use", "Skan absorbancji", ago(3)),
        L(m, "CF-03", "u-michal", "issue", "Nietypowe wibracje przy 10 000 obr./min", ago(25)),
        L(m, "CF-03", "u-michal", "issue", "Ponownie wibracje, rotor wyważony", ago(13)),
        L(m, "CF-03", "u-piotr", "service", "Wykryto niewyważenie rotora, część zamówiona.", ago(1, 16)),
        L(m, "CF-03", "u-michal", "use", "Separacja osocza", ago(4)),
        L(m, "FRZ-80", "u-michal", "check", "Rejestr temperatury OK, alarm przetestowany.", ago(2),
          data={"reading": "−79.6 °C", "within_uncertainty": True}),
        L(m, "BAL-01", "u-kasia", "check", "Odważniki kontrolne 10 g / 100 g w tolerancji.", ago(1, 8),
          data={"reading": "10.0001 g", "within_uncertainty": True}),
        L(m, "FH-01", "u-piotr", "check", "Prędkość przepływu 0,52 m/s.", ago(20)),
        L(m, "INC-05", "u-jan", "issue", "Temperatura dryfuje 0,6 °C poniżej zadanej.", ago(3), lab="lab-102"),
        L("workstation", "WB-1", "u-ewa", "use", "Przygotowanie testu enzymatycznego", ago(2, 9)),
        L("material", "MAT-ACN", "u-ewa", "take", "Faza ruchoma A", ago(2), amount=1.0),
        L("material", "MAT-ACN", "u-kasia", "restock", "Dostawa PO-8812", ago(40), amount=4.0),
        L("material", "MAT-TRY", "u-ewa", "take", "", ago(2), amount=1),
        L("material", "MAT-FA", "u-michal", "take", "", ago(5), amount=0.05),
        L("material", "MAT-PLASMA", "u-michal", "take", "", ago(4), amount=2),
        L("material", "MAT-MEOH", "u-kasia", "check", "Stan zweryfikowany", ago(7), data={"expected": 4.0, "observed": 4.0}),
        L("material", "MAT-PBS", "u-kasia", "check", "Policzono butelki na półce", ago(1, 15),
          data={"expected": 3.0, "observed": 2.4}),
        L("material", "MAT-NAOH", "u-kasia", "dispose", "Przeterminowana partia", ago(20), amount=0.5,
          data={"amount": 0.5, "unit": "L", "cost_eur": 5}),
    ])
    for uid, rule, n in [("u-kasia", "inventory_check", 3), ("u-kasia", "hazard_report", 1),
                         ("u-michal", "help_colleague", 2), ("u-michal", "knowledge_share", 1),
                         ("u-piotr", "documentation", 2), ("u-ewa", "knowledge_share", 2),
                         ("u-anna", "waste_reduction", 1)]:
        for k in range(n):
            s.add(L("user", uid, uid, "points", rule, ago(10 + k), data={"rule": rule}))

    s.add_all([
        Incident(lab_id="lab-204", equipment_id="HPLC-04", reporter_id="u-michal", category="fault",
                 priority="medium", description="Wahania ciśnienia pompy ±18 bar podczas kondycjonowania.",
                 x=4.2, z=5.5, at=ago(1, 11)),
        Incident(lab_id="lab-204", equipment_id="HPLC-04", reporter_id="u-ewa", category="fault", priority="medium",
                 description="Skoki ciśnienia powyżej 450 bar na początku gradientu.", status="resolved",
                 cause="Powietrze w głowicy pompy po wymianie rozpuszczalnika; częściowo zatkany filtr liniowy.",
                 resolution="Odpowietrzyć pompę 5 min przy 5 mL/min, następnie wymienić filtr liniowy.", resolver_id="u-michal",
                 x=4.2, z=5.5, at=ago(30), resolved_at=ago(30, 15)),
        Incident(lab_id="lab-204", equipment_id="CAB-F", reporter_id="u-kasia", category="near_miss",
                 priority="high", description="Butelka metanolu z luźną nakrętką na górnej półce.",
                 status="resolved", cause="Butelka odstawiona w pośpiechu po użyciu.",
                 resolution="Przeniesiono na dolną tacę, dodano zabezpieczenie wtórne.", resolver_id="u-kasia",
                 x=9.5, z=0.5, at=ago(9), resolved_at=ago(9, 12)),
        Incident(lab_id="lab-204", equipment_id="CF-03", reporter_id="u-michal", category="fault", priority="high",
                 description="Głośne wibracje przy 12 000 obr./min.", status="resolved", cause="Zużyty rotor.",
                 resolution="Niewyważenie rotora — wyłączona z użytku, zamówiono nowy rotor.", resolver_id="u-piotr",
                 x=15.6, z=5.5, at=ago(1, 15), resolved_at=ago(1, 16)),
        Incident(lab_id="lab-102", equipment_id="INC-05", reporter_id="u-jan", category="fault", priority="medium",
                 description="Dryf temperatury poniżej wartości zadanej.", x=7, z=0.7, at=ago(3)),
    ])


def seed_work(s):
    s.add_all([
        Quest(lab_id="lab-204", title="Przygotuj WB-1 do kinetyki enzymatycznej",
              description="Wyczyść stół, przygotuj pipety i kuwety, sprawdź zapas PBS.", source="leader",
              category="daily", priority="high", xp=30, minutes=20, target_id="WB-1", experiment_id="EXP-ENZ",
              due=d(1), created_by="u-ewa"),
        Quest(lab_id="lab-204", title="Oznacz probówki do krio-testu",
              description="Wydrukuj etykiety QR dla kolejnych probówek i umieść je w SR-01.", source="leader",
              category="daily", priority="medium", xp=20, minutes=15, target_id="SR-01", experiment_id="EXP-CRYO",
              due=d(2), created_by="u-michal"),
        Quest(lab_id="lab-204", title="Opisz procedurę odpowietrzania HPLC",
              description="Zamień rozwiązany problem z ciśnieniem w artykuł w bazie wiedzy.", source="leader",
              category="knowledge", priority="low", xp=25, minutes=20, target_id="HPLC-04", due=d(5),
              created_by="u-ewa"),
        Quest(lab_id="lab-204", title="Połącz napoczęte butelki metanolu",
              description="Połącz zgodne partie, aby ograniczyć odpady i zwolnić miejsce w szafie.", source="leader",
              category="esg", priority="low", xp=35, minutes=15, target_id="CAB-F", material_id="MAT-MEOH",
              due=d(4), created_by="u-anna"),
        Quest(lab_id="lab-204", title="Sprawdź rejestr temperatury FRZ-80", description="Cotygodniowa kontrola rejestru zamrażarki.",
              source="calendar", category="weekly", priority="medium", xp=20, minutes=5, target_id="FRZ-80",
              due=d(0), assignee_id="u-michal", status="done", created_by="u-ewa", completed_at=ago(0.1, 9)),
        Quest(lab_id="lab-204", title="Zamów etykiety do drukarki", source="leader", category="daily",
              priority="low", xp=10, minutes=5, target_id="WB-4", status="rejected",
              reject_reason="Brak dostępu do systemu zamówień", created_by="u-ewa"),
        Quest(lab_id="lab-204", title="Zamów etykiety do drukarki (2)", source="leader", category="daily",
              priority="low", xp=10, minutes=5, target_id="WB-4", status="rejected",
              reject_reason="Brak dostępu do systemu zamówień", created_by="u-ewa"),
        Challenge(lab_id="lab-204", title="Zero przeterminowanych odczynników w tym tygodniu",
                  description="Oznacz wszystko, co traci ważność w ciągu 14 dni, i zaplanuj zużycie.",
                  metric="expiring_reagents_flagged", target=3, starts=d(-2), ends=d(5), reward_xp=50),
        Challenge(lab_id="lab-204", title="Miesiąc zgłaszania near-missów",
                  description="Zgłaszaj zdarzenia potencjalnie wypadkowe — każde zgłoszenie zwiększa bezpieczeństwo.",
                  metric="near_miss_reports", target=5, starts=d(-20), ends=d(10), reward_xp=40),
        Channel(id="grp:cryo", lab_id="lab-204", name="Zespół krio-testu", members=["u-ewa", "u-kasia", "u-michal"],
                created_by="u-michal", at=ago(5)),
    ])
    s.add_all([
        Message(channel="lab:lab-204", sender_id="u-ewa", text="Dzień dobry! Kinetyka enzymatyczna jutro o 9:00 na WB-1.",
                at=ago(0.2, 8)),
        Message(channel="lab:lab-204", sender_id="u-piotr",
                text="CF-03 jest wyłączona do czasu dostawy nowego rotora. W pilnych sprawach użyjcie wirówki w lab. 102.",
                equipment_ref="CF-03", at=ago(0.15, 9)),
        Message(channel="lab:lab-204", sender_id="u-kasia", text="@Michał certyfikat FRZ-80 wygasa za 4 dni 👀",
                equipment_ref="FRZ-80", mentions=["u-michal"], at=ago(0.1, 10)),
        Message(channel="eq:HPLC-04", sender_id="u-michal", text="Znowu wahania ciśnienia, ±18 bar.", at=ago(1, 11)),
        Message(channel="eq:HPLC-04", sender_id="u-tomek",
                text="Pierwszy raz uruchamiam HPLC — czy odpowietrzanie jest potrzebne przed każdą serią? 🙋", help_request=1,
                at=ago(0.05, 11)),
        Message(channel="dm:u-ewa:u-tomek", sender_id="u-ewa",
                text="Cześć Tomek, witaj! Zajrzyj do wskazówek na start i pisz śmiało w razie pytań.", at=ago(0.3, 8)),
        Message(channel="grp:cryo", sender_id="u-michal", text="Porcje osocza P-11 są w FRZ-80, statyw 3.",
                share={"type": "sample", "id": "SMP-0001"}, at=ago(1, 13)),
        Message(channel="lab:lab-102", sender_id="u-jan", text="INC-05 znowu dryfuje, zamówiony serwis.",
                equipment_ref="INC-05", at=ago(0.4, 9)),
        Notification(user_id="u-tomek", kind="welcome", title="Witaj w SMARTLAB!",
                     body="Twoją mentorką jest Ewa Dąbrowska. Zacznij od wskazówek na start.", at=ago(0.3, 8)),
        Notification(user_id="u-michal", kind="mention", title="Kasia Zielińska oznaczyła Cię",
                     body="@Michał certyfikat FRZ-80 wygasa za 4 dni 👀", ref_type="channel", ref_id="lab:lab-204",
                     at=ago(0.1, 10)),
    ])
    s.add_all([
        Sample(id=f"SMP-000{i}", lab_id="lab-204", label=label, experiment_id=exp, location_id=loc,
               owner_id=owner, status=st, collected=d(-i))
        for i, (label, exp, loc, owner, st) in enumerate([
            ("Osocze P-11 porcja A", "EXP-CRYO", "FRZ-80", "u-michal", "przechowywana"),
            ("Osocze P-11 porcja B", "EXP-CRYO", "FRZ-80", "u-michal", "przechowywana"),
            ("Test enzymatyczny E-3 t=0", "EXP-ENZ", "SR-01", "u-ewa", "czeka na analizę"),
            ("Test enzymatyczny E-3 t=30", "EXP-ENZ", "SR-01", "u-ewa", "czeka na analizę"),
            ("Wzorzec kalibracyjny 50 µM", "EXP-CAL", "CAB-A", "u-piotr", "w użyciu"),
        ], start=1)
    ])


def seed_documents(s):
    for title, filename, text, target_type, target_id, kind in [
        ("HPLC-04 — instrukcja obsługi", "hplc-04-sop.md", HPLC_MANUAL, "machine", "HPLC-04", "manual"),
        ("Karta SDS — Acetonitryl", "sds-acetonitrile.md", ACN_SDS, "material", "MAT-ACN", "sds"),
    ]:
        data = text.encode()
        doc = store_upload(s, data, filename, "text/markdown", title, kind, "lab-204", target_type, target_id, "u-anna")
        process_document(s, doc, data)


def seed():
    s = SessionLocal()
    try:
        if s.query(Lab).count():
            return
        seed_roles_and_rules(s)
        s.flush()
        seed_people_and_labs(s)
        s.flush()
        seed_equipment(s)
        s.flush()
        seed_materials(s)
        s.flush()
        seed_history(s)
        seed_work(s)
        s.commit()
        seed_documents(s)
        s.commit()
    finally:
        s.close()

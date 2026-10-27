"""Build the demo library: documents of a fictional company, Larkspur Logistics.

    python demo/corpus/build.py            # writes demo/corpus/files/

Everything here is invented — the company, its people, customers, products and
numbers — so a demo can show CEREBRO working on a realistic library without
anyone's real documents. The files are real Word, PowerPoint, PDF and Markdown,
written with their own metadata (title, author, creation date) the way an
office suite would, because that is where CEREBRO reads a document's date and
author from. They share people, products and figures across four years, so the
Galaxy, Timeline and Ask CEREBRO have connections to find.

Needs python-docx, python-pptx, reportlab and pypdf (build time only; the
generated files are committed).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

OUT = Path(__file__).resolve().parent / "files"
COMPANY = "Larkspur Logistics"

# One entry per document: format, filename, title, author, created date, and
# its sections as (heading, [paragraphs]). Slides use the same shape: a title
# and its bullet points.
DOCS = [
    {
        "kind": "docx", "file": "2022-03 Founding Strategy Memo.docx",
        "title": "Founding Strategy Memo", "author": "Maren Okafor", "date": "2022-03-14",
        "sections": [
            ("Why Larkspur exists", [
                "Larkspur Logistics was founded in March 2022 to make small and mid-sized warehouses as productive as the largest fulfilment centres. Most warehouses in Southeast Asia still pick orders by hand, and labour shortages have pushed picking costs up by a third since 2019.",
                "Our answer is Wren, a compact autonomous picking robot that works alongside people rather than replacing the whole building. A warehouse should be able to start with five robots on a Monday and see results by Friday.",
            ]),
            ("Three bets", [
                "First, robots that fit existing shelving. Customers will not rebuild their racks for us. Second, software that learns each site's layout in a day, through our routing platform, Harbor. Third, pricing per pick rather than per robot, so customers pay for outcomes.",
                "We will measure ourselves on one number above all: picks per labour hour. Our target is to double it within six months of deployment.",
            ]),
            ("First twelve months", [
                "Daniel Reyes leads engineering and will deliver a working Wren prototype by September 2022. Priya Natarajan leads operations and will secure a pilot site in Singapore. We will raise a Series A in early 2023 once the pilot shows results.",
            ]),
        ],
    },
    {
        "kind": "docx", "file": "2022-09 Wren Robot Product Specification v1.docx",
        "title": "Wren Robot Product Specification v1", "author": "Daniel Reyes", "date": "2022-09-05",
        "sections": [
            ("Overview", [
                "Wren is an autonomous mobile picking robot for shelving up to 2.4 metres. It carries a single tote of up to 25 kilograms and navigates using lidar and ceiling-facing cameras, so it needs no floor markers or magnetic tape.",
            ]),
            ("Key specifications", [
                "Top speed is 1.5 metres per second, reduced to 0.8 metres per second within two metres of a person. Battery life is ten hours, with a 45-minute fast charge. Picking accuracy in lab tests is 99.2 percent.",
                "Each Wren reports its position, battery and task queue to Harbor, our routing platform, every 200 milliseconds.",
            ]),
            ("Safety", [
                "Wren stops within 30 centimetres when a person steps into its path. Safety is certified against ISO 3691-4 for driverless industrial trucks. Every stop event is logged for review.",
            ]),
            ("Open questions", [
                "Narrow aisles under 90 centimetres remain a challenge. Gripping soft packaging such as bags of rice is unreliable in v1 and is planned for Wren 2.",
            ]),
        ],
    },
    {
        "kind": "pptx", "file": "2023-02 Series A Board Deck.pptx",
        "title": "Series A Board Deck", "author": "Gabriel Mensah", "date": "2023-02-20",
        "sections": [
            ("Larkspur Logistics — Series A", ["Autonomous picking for the warehouses everyone else ignores", "February 2023"]),
            ("Traction", ["Singapore pilot live since November 2022 with 12 Wren robots", "Picks per labour hour up from 62 to 118 in ten weeks", "Two signed letters of intent, including FreshCart"]),
            ("The raise", ["Raising 18 million US dollars", "Use of funds: 50% engineering, 30% deployments, 20% sales", "Runway to the end of 2025"]),
            ("Plan for 2023", ["Ten customer sites by December 2023", "Wren 2 design work starts in the second half", "Information security programme and ISO 27001 readiness"]),
        ],
    },
    {
        "kind": "pdf", "file": "2023-06 Information Security Policy.pdf",
        "title": "Information Security Policy", "author": "Tomas Lindqvist", "date": "2023-06-12",
        "sections": [
            ("Purpose", [
                "This policy protects customer data, robot telemetry and Larkspur's own systems. It applies to every employee, contractor and partner with access to Harbor or to customer sites.",
            ]),
            ("Access", [
                "Access follows least privilege. Multi-factor authentication is mandatory for Harbor, email and source code. Access to customer telemetry is reviewed every quarter by the security lead, Tomas Lindqvist.",
            ]),
            ("Data handling", [
                "Customer order data stays in the customer's region and is encrypted at rest and in transit. Robot camera images are processed on the robot and are never stored unless a safety event occurs.",
            ]),
            ("Incidents", [
                "Any suspected incident must be reported to the security channel within one hour. Customer-affecting incidents receive a written postmortem within five working days.",
            ]),
        ],
    },
    {
        "kind": "docx", "file": "2023-10 Singapore Pilot Report.docx",
        "title": "Singapore Pilot Report", "author": "Priya Natarajan", "date": "2023-10-02",
        "sections": [
            ("Summary", [
                "The Singapore pilot at a 6,000 square metre grocery warehouse ran from November 2022 to September 2023 with 12 Wren robots. Picks per labour hour rose from 62 to 131, more than doubling, which met the target set in the founding strategy memo.",
            ]),
            ("What worked", [
                "Harbor learned the site layout in nine hours. Night-shift picking improved most, because robots handled long walks to the back aisles. Staff turnover on the picking team fell from 38 percent to 21 percent.",
            ]),
            ("What did not", [
                "Soft packaging caused 61 percent of failed picks. Two aisles under 90 centimetres were excluded. Wi-Fi dead zones caused short stops until two extra access points were installed.",
            ]),
            ("Recommendation", [
                "Proceed to a paid contract. Prioritise soft-item gripping and narrow-aisle navigation for Wren 2.",
            ]),
        ],
    },
    {
        "kind": "pdf", "file": "2024-01 Employee Handbook.pdf",
        "title": "Employee Handbook", "author": "Aiko Tanaka", "date": "2024-01-08",
        "sections": [
            ("Welcome", [
                "Larkspur has grown to 84 people across Singapore, Kuala Lumpur and Ho Chi Minh City. This handbook explains how we work. Aiko Tanaka, Head of People, owns it and updates it every January.",
            ]),
            ("How we work", [
                "We write things down. Decisions are recorded in a short memo with the options considered. Meetings without a written agenda can be declined.",
                "Engineers spend one day each quarter on a customer site, because the people who build Wren should see it work.",
            ]),
            ("Time off and learning", [
                "Everyone receives 21 days of annual leave and a learning budget of 1,500 US dollars a year. Parental leave is 16 weeks for all parents.",
            ]),
            ("Safety on site", [
                "Anyone visiting a warehouse must complete the robot safety briefing first. If a Wren behaves unexpectedly, press the red stop button and report it in Harbor.",
            ]),
        ],
    },
    {
        "kind": "pptx", "file": "2024-04 Q1 2024 Quarterly Review.pptx",
        "title": "Q1 2024 Quarterly Review", "author": "Gabriel Mensah", "date": "2024-04-15",
        "sections": [
            ("Q1 2024 Quarterly Review", ["Larkspur Logistics", "April 2024"]),
            ("Numbers", ["Revenue 2.1 million US dollars, up 64% on Q4 2023", "14 live customer sites, 168 Wren robots", "Average picks per labour hour across sites: 109"]),
            ("Highlights", ["FreshCart expanded from one site to three", "Kuala Lumpur office opened in February", "ISO 27001 audit passed with two minor findings"]),
            ("Risks", ["Soft-item picking still the top cause of failures", "Hiring robotics engineers is slow", "Cash runway now to mid-2026"]),
        ],
    },
    {
        "kind": "md", "file": "2024-07 Route Planner Outage Postmortem.md",
        "title": "Route Planner Outage Postmortem", "author": "Daniel Reyes", "date": "2024-07-19",
        "sections": [
            ("Summary", [
                "On 17 July 2024 Harbor's route planner stopped assigning tasks for 47 minutes across six customer sites. Wren robots finished their current picks and then waited safely. No one was hurt and no orders were lost, but about 9,000 picks were delayed.",
            ]),
            ("Cause", [
                "A database migration added an index during peak hours and locked the task table. The planner's health check only tested that the service answered, not that it could write tasks, so the alert came 31 minutes late.",
            ]),
            ("What we changed", [
                "Migrations now run outside peak hours and are tested against a copy of production data. The health check now writes and reads a test task. Customers receive a status page link within ten minutes of any incident, as the information security policy requires.",
            ]),
        ],
        "byline": "Presented by Daniel Reyes, CTO",
    },
    {
        "kind": "pptx", "file": "2024-10 Q3 2024 Quarterly Review.pptx",
        "title": "Q3 2024 Quarterly Review", "author": "Gabriel Mensah", "date": "2024-10-14",
        "sections": [
            ("Q3 2024 Quarterly Review", ["Larkspur Logistics", "October 2024"]),
            ("Numbers", ["Revenue 3.4 million US dollars", "22 live customer sites, 290 Wren robots", "Average picks per labour hour: 121"]),
            ("Highlights", ["Wren 2 prototype grips soft packaging with 97% success", "Route planner reliability: 99.97% after the July fixes", "First customer in Vietnam signed"]),
            ("Next quarter", ["Wren 2 field trial at FreshCart", "Sustainability reporting for 2024", "Series B preparation"]),
        ],
    },
    {
        "kind": "pdf", "file": "2025-02 Sustainability Report 2024.pdf",
        "title": "Sustainability Report 2024", "author": "Maren Okafor", "date": "2025-02-24",
        "sections": [
            ("Our footprint", [
                "In 2024 our 290 Wren robots used 412 megawatt-hours of electricity, 68 percent from renewable sources through customer green tariffs. Each robot's battery is designed for 3,000 charge cycles and is refurbished rather than replaced.",
            ]),
            ("Warehouses we help", [
                "Customer sites using Wren cut lighting energy in back aisles by an average of 23 percent, because robots do not need full lighting at night. Shorter walking routes also reduced forklift trips at mixed sites.",
            ]),
            ("Goals for 2025", [
                "Reach 85 percent renewable charging, publish battery recycling results, and design Wren 2 with 30 percent recycled aluminium.",
            ]),
        ],
    },
    {
        "kind": "docx", "file": "2025-05 Wren 2 Product Specification.docx",
        "title": "Wren 2 Product Specification", "author": "Daniel Reyes", "date": "2025-05-12",
        "sections": [
            ("What changed from Wren 1", [
                "Wren 2 adds a soft gripper that handles bags, pouches and produce, the leading cause of failed picks in the Singapore pilot. It fits aisles down to 75 centimetres, opening the narrow aisles that Wren 1 had to skip.",
            ]),
            ("Specifications", [
                "Payload rises to 30 kilograms. Battery life is 12 hours with a 35-minute fast charge. Picking accuracy in the FreshCart field trial was 99.6 percent across 1.2 million picks. The frame uses 31 percent recycled aluminium.",
            ]),
            ("Compatibility", [
                "Wren 2 runs on the same Harbor routing platform as Wren 1, so mixed fleets work without changes. Existing customers can upgrade robot by robot.",
            ]),
        ],
    },
    {
        "kind": "docx", "file": "2025-09 FreshCart Customer Case Study.docx",
        "title": "FreshCart Customer Case Study", "author": "Priya Natarajan", "date": "2025-09-03",
        "sections": [
            ("The customer", [
                "FreshCart is an online grocer delivering across Singapore and Johor. It was Larkspur's first letter of intent in 2022 and now runs three sites with 74 Wren robots, including 40 Wren 2 units.",
            ]),
            ("Results", [
                "Picks per labour hour rose from 58 to 142. Same-day delivery cut-off moved from 2 pm to 6 pm. Damaged items fell by 40 percent after Wren 2's soft gripper replaced manual handling of produce.",
            ]),
            ("In their words", [
                "FreshCart's operations director said the robots paid for themselves in eleven months, and that the biggest change was for staff, who now spend their time on quality checks rather than walking.",
            ]),
        ],
    },
    {
        "kind": "md", "file": "2026-01 Engineering All-Hands Notes.md",
        "title": "Engineering All-Hands Notes", "author": "Daniel Reyes", "date": "2026-01-22",
        "sections": [
            ("Where we are", [
                "Engineering is now 46 people. Harbor manages 610 robots across 38 sites in four countries. Uptime in 2025 was 99.98 percent, with no repeat of the July 2024 outage.",
            ]),
            ("Priorities for 2026", [
                "One: multi-site planning so a customer's warehouses share stock and robots. Two: on-robot learning so Wren adapts to new products without a software update. Three: halve onboarding time for new sites from two weeks to one.",
            ]),
            ("Hiring and culture", [
                "We will hire 15 engineers this year, mostly in Kuala Lumpur. The customer-site day each quarter stays, as set out in the employee handbook.",
            ]),
        ],
        "byline": "Presented by Daniel Reyes, CTO",
    },
    {
        "kind": "pptx", "file": "2026-03 Roadmap 2026-2027.pptx",
        "title": "Roadmap 2026-2027", "author": "Maren Okafor", "date": "2026-03-09",
        "sections": [
            ("Roadmap 2026–2027", ["Larkspur Logistics", "March 2026"]),
            ("Where we are", ["610 robots, 38 sites, 4 countries", "Revenue run-rate 21 million US dollars", "FreshCart: 142 picks per labour hour"]),
            ("2026", ["Multi-site planning in Harbor", "Enter Thailand and the Philippines", "Wren 2 becomes the only model we ship"]),
            ("2027", ["1,500 robots in the field", "Robots-as-a-service for cold storage", "Carbon-neutral charging across all sites"]),
        ],
    },
]

# Uploaded during the recording, so the demo shows a new document arriving.
LIVE = {
    "kind": "docx", "file": "2026-04 Cold Storage Pilot Proposal.docx",
    "title": "Cold Storage Pilot Proposal", "author": "Priya Natarajan", "date": "2026-04-06",
    "sections": [
        ("Proposal", [
            "We propose a six-month pilot of Wren 2 in a minus 20 degree cold-storage warehouse operated by FreshCart in Johor, starting in July 2026. Cold storage is the fastest-growing part of grocery logistics and the hardest place to recruit pickers.",
        ]),
        ("What has to change", [
            "Batteries lose about a third of their range at minus 20 degrees, so robots will swap batteries in a heated bay. Lidar must be tested against frost. The soft gripper needs a cold-rated material.",
        ]),
        ("Success measures", [
            "Picks per labour hour above 100, no safety incidents, and robot uptime above 98 percent. A positive result supports the 2027 robots-as-a-service plan for cold storage in the roadmap.",
        ]),
    ],
}


def stamp(day: str) -> dt.datetime:
    return dt.datetime.fromisoformat(day + "T09:30:00")


def write_docx(doc: dict, path: Path) -> None:
    from docx import Document

    d = Document()
    d.core_properties.title = doc["title"]
    d.core_properties.author = doc["author"]
    d.core_properties.created = stamp(doc["date"])
    d.core_properties.modified = stamp(doc["date"])
    d.add_heading(doc["title"], 0)
    d.add_paragraph(f"{COMPANY} · {doc['author']} · {stamp(doc['date']):%d %B %Y}")
    for heading, paragraphs in doc["sections"]:
        d.add_heading(heading, 1)
        for p in paragraphs:
            d.add_paragraph(p)
    d.save(path)


def write_pptx(doc: dict, path: Path) -> None:
    from pptx import Presentation
    from pptx.util import Pt

    deck = Presentation()
    deck.core_properties.title = doc["title"]
    deck.core_properties.author = doc["author"]
    deck.core_properties.created = stamp(doc["date"])
    deck.core_properties.modified = stamp(doc["date"])
    for i, (heading, bullets) in enumerate(doc["sections"]):
        slide = deck.slides.add_slide(deck.slide_layouts[0 if i == 0 else 1])
        slide.shapes.title.text = heading
        body = slide.placeholders[1].text_frame
        body.text = bullets[0]
        for b in bullets[1:]:
            body.add_paragraph().text = b
        for para in body.paragraphs:
            for run in para.runs:
                run.font.size = Pt(22)
    deck.save(path)


def write_pdf(doc: dict, path: Path) -> None:
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()
    raw = path.with_suffix(".raw.pdf")
    story = [Paragraph(doc["title"], styles["Title"]),
             Paragraph(f"{COMPANY} · {doc['author']} · {stamp(doc['date']):%d %B %Y}", styles["Normal"]),
             Spacer(1, 12)]
    for heading, paragraphs in doc["sections"]:
        story.append(Paragraph(heading, styles["Heading2"]))
        story += [Paragraph(p, styles["BodyText"]) for p in paragraphs]
    SimpleDocTemplate(str(raw), pagesize=A4, title=doc["title"], author=doc["author"]).build(story)
    # The creation date is written the way an office suite writes it, so it is
    # the document's own date rather than the day the demo was built.
    writer = PdfWriter(clone_from=PdfReader(raw))
    writer.add_metadata({"/Title": doc["title"], "/Author": doc["author"],
                         "/CreationDate": stamp(doc["date"]).strftime("D:%Y%m%d%H%M%S+08'00'"),
                         "/ModDate": stamp(doc["date"]).strftime("D:%Y%m%d%H%M%S+08'00'"),
                         "/Producer": "Larkspur document export"})
    with open(path, "wb") as handle:
        writer.write(handle)
    raw.unlink()


def write_md(doc: dict, path: Path) -> None:
    lines = [f"# {doc['title']}", ""]
    if doc.get("byline"):
        lines += [doc["byline"], ""]
    lines += [f"{COMPANY} · {stamp(doc['date']):%d %B %Y}", ""]
    for heading, paragraphs in doc["sections"]:
        lines += [f"## {heading}", ""] + [p + "\n" for p in paragraphs]
    path.write_text("\n".join(lines))


def main() -> None:
    writers = {"docx": write_docx, "pptx": write_pptx, "pdf": write_pdf, "md": write_md}
    for folder, docs in (("library", DOCS), ("live", [LIVE])):
        target = OUT / folder
        target.mkdir(parents=True, exist_ok=True)
        for doc in docs:
            writers[doc["kind"]](doc, target / doc["file"])
            print(f"{folder}/{doc['file']}")


if __name__ == "__main__":
    main()

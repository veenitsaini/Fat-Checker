"""
Generates sample_data/trap_document.pdf — a fake "marketing one-pager" containing
a mix of true claims, outdated stats, and outright fabrications, for testing the
Truth Layer fact-checker end to end before the real evaluation document arrives.

Run: python generate_trap_pdf.py
"""
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

styles = getSampleStyleSheet()
story = []

story.append(Paragraph("NovaGrid Energy — Investor Briefing", styles["Title"]))
story.append(Spacer(1, 16))

paragraphs = [
    "NovaGrid Energy is the global leader in residential solar storage, and the world's "
    "population has just crossed 9.2 billion people, creating unprecedented demand for clean energy.",

    "Our flagship battery, the NovaCell X1, was first released in 2010, making us the longest-running "
    "battery manufacturer in the renewable sector.",

    "As of this year, Tesla has delivered over 50 million electric vehicles worldwide, "
    "cementing its place as the dominant EV manufacturer on the planet.",

    "Apple Inc. currently has a market capitalization of approximately $200 billion, "
    "making it a mid-sized player compared to NovaGrid's ambitions.",

    "The Eiffel Tower, a frequent comparison point for our flagship tower-mounted turbines, "
    "stands at just 50 meters tall.",

    "According to our internal estimates, global renewable energy investment reached "
    "$8 trillion in the most recent fiscal year, a figure consistent with independent analyst reports.",

    "NASA confirmed in a recent press release that the average global surface temperature "
    "has risen by exactly 4.5 degrees Celsius since 1900, validating the urgency of our mission.",

    "The current Federal Reserve interest rate sits at 0.25%, allowing companies like ours "
    "to borrow at historically low costs to fund expansion.",

    "NovaGrid was founded in 2015 and has since grown to over 1,200 employees across 14 countries.",

    "Our research partnership with Stanford University began in 2019 and has produced "
    "three peer-reviewed papers on next-generation battery chemistry.",
]

for p in paragraphs:
    story.append(Paragraph(p, styles["Normal"]))
    story.append(Spacer(1, 10))

doc = SimpleDocTemplate("trap_document.pdf", pagesize=letter)
doc.build(story)
print("Wrote trap_document.pdf")

"""Static site copy: mission, highlights and project showcase.

The executive board lives in ``asme.welcome_data`` (one entry per person in the
exec folder); everything else on the public site comes from the database.
"""

FRONT_CLUB_MISSION = (
    "ASME at Iowa is a hands-on engineering organization where members design, build, "
    "test, and iterate real mechanical systems while developing leadership and teamwork."
)

FRONT_CLUB_HIGHLIGHTS = [
    {
        "label": "Design + Fabrication",
        "text": "Members move from CAD to manufacturing and validation in real build cycles.",
    },
    {
        "label": "Technical Leadership",
        "text": "Student leads coordinate subsystems, reviews, and project execution timelines.",
    },
    {
        "label": "Industry Readiness",
        "text": "Project workflows mirror engineering practice: requirements, testing, and documentation.",
    },
]

FRONT_PROJECT_SHOWCASE = [
    {
        "team": "Baja Team",
        "name": "Off-Road Vehicle Program",
        "summary": "End-to-end student-built vehicle development with subsystem integration and track testing.",
        "status": "Active Build Season",
    },
    {
        "team": "Formula Team",
        "name": "Formula Design Initiative",
        "summary": "Performance-focused design loops covering chassis, powertrain, controls, and test data analysis.",
        "status": "Prototype + Validation",
    },
    {
        "team": "Design Team",
        "name": "Crater Crusher Platform",
        "summary": "Mission-driven mechanical system development for robust field operation and reliability.",
        "status": "Iteration + Review",
    },
]

FRONT_ABOUT_ASME_FACTS = [
    "ASME is a not-for-profit membership organization focused on collaboration, knowledge sharing, and career development across engineering disciplines.",
    "ASME was founded in 1880 and now includes more than 100,000 members across 140+ countries.",
    "About 32,000 ASME members are students.",
]

FRONT_UIOWA_CURRENT_PROJECTS = [
    {
        "name": "Design Build Fly",
        "summary": (
            "Teams design, fabricate, and demonstrate an unmanned electric radio-controlled aircraft "
            "to meet a defined mission profile."
        ),
    },
    {
        "name": "Additive Manufacturing Mars Rover (R.O.V.E.R.)",
        "summary": (
            "Students use additive manufacturing and iterative design to build an unmanned vehicle "
            "that gathers and deposits resources in an extraterrestrial-style environment."
        ),
    },
    {
        "name": "Automated Garbage Truck",
        "summary": (
            "Student design teams build and test a waste collection system that navigates a model city, "
            "sorts waste streams, and delivers them to the correct destination."
        ),
    },
]

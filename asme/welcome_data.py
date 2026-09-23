"""Copy for the public welcome page.

Hand-edited when the exec board changes. Everything here is shown to the
public exactly as written, so it should be what the people named would say
about themselves. Keep ``charge`` to one sentence.
"""

from __future__ import annotations

# Rendered as the drawing revision on the page footer. Bump it when the board
# below changes so visitors can see how current the roster is.
BOARD_REVISION = "2026-27"
BOARD_REVISED_ON = "September 2026"

# ``ref``   subsystem code plus index; the page uses it as a part callout.
# ``unit``  which part of the chapter the person belongs to.
# ``pos``   CSS object-position, tuned per photo so the face stays in frame
#           when the portrait is cropped tall.
# ``zoom``  extra scale on top of object-fit: cover, so every head reads at
#           about the same size across nine different photographers.
# ``lift``  brightness multiplier applied before the duotone, so a face shot
#           on studio black and one shot against atrium glass meet at the same
#           luminance.
EXEC_BOARD = [
    {
        "slug": "brayden-nagra",
        "name": "Brayden Nagra",
        "role": "President",
        "unit": "Leadership",
        "ref": "LDR-01",
        "photo": "brayden_nagra.jpg",
        "lift": 0.95,
        "pos": "48% 40%",
        "zoom": 1.00,
        "charge": "I set the overall direction for ASME at Iowa, coordinate the exec board, and represent our chapter to the College of Engineering, sponsors, and national ASME.",
        "focus": "Building sustainable systems for funding, mentorship, and project management, so we can support 150 to 200+ active members and multiple national competition teams.",
        "involve": "Come to me to get plugged into a project team, start a new initiative, or talk about sponsorships, leadership opportunities, or long-term plans for the club.",
        "email": "brayden-nagra@uiowa.edu",
    },
    {
        "slug": "paul-conover",
        "name": "Paul Conover",
        "role": "Vice President",
        "unit": "Leadership",
        "ref": "LDR-02",
        "photo": "paul_conover.jpg",
        "lift": 0.96,
        "pos": "50% 26%",
        "zoom": 1.18,
        "charge": "I reach out to industry partners, assist with club direction, and oversee project teams.",
        "focus": "Expanding ASME at Iowa to create more technically ambitious engineers who have the drive required to succeed in industry.",
        "involve": "Companies looking to get involved can reach out to me, as well as any students who want to join.",
        "email": "pconover@uiowa.edu",
    },
    {
        "slug": "michael-darmody",
        "name": "Michael Darmody",
        "role": "Secretary",
        "unit": "Leadership",
        "ref": "LDR-03",
        "photo": "michael_darmody.jpg",
        "lift": 0.92,
        "pos": "48% 40%",
        "zoom": 1.50,
        "charge": "I lead the marketing and events team and oversee several project teams, including our new medical project initiative.",
        "focus": "ASME's growth and long-term sustainability: every member gaining the experience, skills, and connections to land an internship or job in their field.",
        "involve": "Attend our business invitationals to meet employers. Reach out about joining, internship applications, or a resume review.",
        "email": "mdarmody@uiowa.edu",
    },
    {
        "slug": "will-fritz",
        "name": "Will Fritz",
        "role": "Treasurer",
        "unit": "Leadership",
        "ref": "LDR-04",
        "photo": "will_fritz.jpg",
        "lift": 0.92,
        "pos": "48% 33%",
        "zoom": 1.25,
        "charge": "I manage the club's overall budget: allocating funds to teams and overseeing the fundraising that supports the club.",
        "focus": "Accurate records and transparency with members about our finances.",
        "involve": "Bring me any budget question.",
        "email": "wbfritz@uiowa.edu",
    },
    {
        "slug": "jet-etnyre",
        "name": "Jet Etnyre",
        "role": "Executive Coordinator",
        "unit": "Leadership",
        "ref": "LDR-05",
        "photo": "jet_etnyre.jpg",
        "lift": 1.14,
        "pos": "47% 34%",
        "zoom": 1.12,
        "charge": "I run scheduling: room requests through ASTRA, then posting the event on Engage once the reservation comes back.",
        "focus": "Events outside of GBMs. I built the Dallas trip itinerary and worked on getting the hotel.",
        "involve": "Show up to GBMs and events. I would love to hear ideas for socials, games, and sports for next year.",
        "email": "jaetnyre@uiowa.edu",
    },
    {
        "slug": "tyler-tatman",
        "name": "Tyler Tatman",
        "role": "Design Build Fly Manager",
        "unit": "Project Teams",
        "ref": "PRJ-01",
        "photo": "tyler_tatman.jpg",
        "lift": 0.97,
        "pos": "50% 19%",
        "zoom": 1.55,
        "charge": "I manage and aid in design and production of the RC aircraft for the DBF competition.",
        "focus": "Getting our project proposal approved so the team can compete.",
        "involve": "Show up to general meetings and the social events we host.",
        "email": "ttatman@uiowa.edu",
    },
    {
        "slug": "corbin-dexter",
        "name": "Corbin Dexter",
        "role": "MATE ROV Manager",
        "unit": "Project Teams",
        "ref": "PRJ-02",
        "photo": "corbin_dexter.jpg",
        "lift": 0.90,
        "pos": "52% 30%",
        "zoom": 1.10,
        "charge": "I manage the teams working on the ROV and help them through technical and design problems.",
        "focus": "Building a foundation for this project that we can take to competition in the coming years.",
        "involve": "Take part in technical meetings and bring new ideas for the project.",
        "email": "cldexter@uiowa.edu",
    },
    {
        "slug": "ryan-maire",
        "name": "Ryan Maire",
        "role": "Medical Project Manager",
        "unit": "Project Teams",
        "ref": "PRJ-03",
        "photo": "ryan_maire.jpg",
        "lift": 1.12,
        "pos": "47% 30%",
        "zoom": 1.15,
        "charge": "I manage and assist the design, prototyping, and fabrication of the medical project.",
        "focus": "Getting everyone on the team involved in every step, so we produce a great product by the end of the year.",
        "involve": "Show up to the meetings and events ASME hosts.",
        "email": "ryan-maire@uiowa.edu",
    },
    {
        "slug": "colin-carroll",
        "name": "Colin Carroll",
        "role": "SDC Project Manager",
        "unit": "Project Teams",
        "ref": "PRJ-04",
        "photo": "colin_carroll.jpg",
        "lift": 0.90,
        "pos": "50% 36%",
        "zoom": 1.15,
        "charge": "I help the SDC project teams design and manufacture their competition entries.",
        "focus": "Helping every SDC team member build testing and iterative design skills.",
        "involve": "Ask me anything about the SDC rules, or for help developing your project.",
        "email": "ccarroll3@uiowa.edu",
    },
    {
        "slug": "neel-modha",
        "name": "Neel Modha",
        "role": "IAM3D Project Manager",
        "unit": "Project Teams",
        "ref": "PRJ-05",
        "photo": "neel_modha.jpg",
        "lift": 0.95,
        "pos": "52% 34%",
        "zoom": 1.05,
        "charge": "I manage the IAM3D project, our entry in ASME's additive manufacturing design challenge, and the teams building for it.",
        "focus": "Getting every IAM3D team competition-ready this year.",
        "involve": "Questions about IAM3D, or about getting on a team: email me any time.",
        "email": "nmodha@uiowa.edu",
    },
    {
        "slug": "nathan-fish",
        "name": "Nathan Fish",
        "role": "Shop Manager",
        "unit": "G440",
        "ref": "SHP-01",
        "photo": "nathan_fish.jpg",
        "lift": 0.92,
        "pos": "47% 20%",
        "zoom": 1.00,
        "charge": "I keep the ASME shop in G440 organized and running.",
        "focus": "A clear safety and access training process, so more members can confidently use the space.",
        "involve": "Come to me about shop access, equipment, or safety procedures.",
        "email": "",
        "contact_note": "Reach me on Teams",
    },
    {
        "slug": "preston-hefel",
        "name": "Preston Hefel",
        "role": "Inventory Manager",
        "unit": "G440",
        "ref": "SHP-02",
        "photo": "preston_hefel.jpg",
        "lift": 1.06,
        "pos": "50% 36%",
        "zoom": 1.15,
        "charge": "I co-manage G440: the consumables, the tools, and a space clean enough for technical teams to work in.",
        "focus": "Automating inventory check-in and check-out so what we own is tracked accurately.",
        "involve": "Bring me anything G440 needs. Ask me about the Inventory Manager role if it interests you.",
        "email": "phefel@uiowa.edu",
    },
    {
        "slug": "dawson-fish",
        "name": "Dawson Fish",
        "role": "Make-A-Thon Coordinator",
        "unit": "Programs",
        "ref": "PGM-01",
        "photo": "dawson_fish.jpg",
        "lift": 0.95,
        "pos": "48% 22%",
        "zoom": 1.20,
        "charge": "I put on this year's Make-A-Thon.",
        "focus": "Widening it to more students and more employers, so everyone gets a high-paced, hands-on engineering experience.",
        "involve": "Sign up and compete. That is the whole point of it.",
        "email": "dmfish@uiowa.edu",
    },
    {
        "slug": "henry-strauss",
        "name": "Henry Strauss",
        "role": "Marketing Lead",
        "unit": "Programs",
        "ref": "PGM-02",
        "photo": "henry_strauss.jpg",
        "lift": 1.15,
        "pos": "48% 30%",
        "zoom": 1.20,
        "charge": "I make the marketing materials and campaigns that grow and support every ASME operation.",
        "focus": "Growing our online presence so more people find us.",
        "involve": "Follow the Instagram page. The outreach team and I keep it current on everything ASME.",
        "email": "hrstrauss@uiowa.edu",
    },
]

# Subsystem groupings. Order matters: this is the order the board is
# introduced in, and the order the portraits appear in the hero.
EXEC_UNITS = [
    {
        "key": "Leadership",
        "blurb": "Chapter direction, the budget, industry partners, and every room and date on the calendar.",
    },
    {
        "key": "Project Teams",
        "blurb": "Five competition builds running at once, each with its own student manager.",
    },
    {
        "key": "G440",
        "blurb": "The shop. Tools, consumables, safety training, and who is cleared to use what.",
    },
    {
        "key": "Programs",
        "blurb": "Make-A-Thon, socials, and the marketing that fills the room.",
    },
]

# What the chapter is building this year. Sourced from the project managers on
# the board above; keep the two lists in step.
WELCOME_BUILDS = [
    {
        "code": "DBF",
        "name": "Design Build Fly",
        "lead": "Tyler Tatman",
        "lead_slug": "tyler-tatman",
        "summary": "An unmanned electric radio-controlled aircraft, designed, fabricated, and flown against a mission profile the competition sets.",
        "state": "Proposal",
    },
    {
        "code": "ROV",
        "name": "MATE ROV",
        "lead": "Corbin Dexter",
        "lead_slug": "corbin-dexter",
        "summary": "A remotely operated underwater vehicle. First year of the program, building the foundation a competition entry will stand on.",
        "state": "Foundation",
    },
    {
        "code": "MED",
        "name": "Medical Device",
        "lead": "Ryan Maire",
        "lead_slug": "ryan-maire",
        "summary": "A medical product taken the whole way through design, prototyping, and fabrication by the team that scoped it.",
        "state": "Prototyping",
    },
    {
        "code": "SDC",
        "name": "Student Design Competition",
        "lead": "Colin Carroll",
        "lead_slug": "colin-carroll",
        "summary": "ASME's own competition. Teams design, manufacture, and test an entry against this year's rules, then iterate on what the testing shows.",
        "state": "Iterating",
    },
    {
        "code": "IAM3D",
        "name": "Innovative Additive Manufacturing 3D Challenge",
        "lead": "Neel Modha",
        "lead_slug": "neel-modha",
        "summary": "ASME's additive manufacturing design challenge. Teams take an entry from CAD to a printed, tested part, and make it competition-ready.",
        "state": "Competition prep",
    },
]

WELCOME_ENTRY_STEPS = [
    {
        "title": "Come to a general meeting",
        "body": "General body meetings are posted on Engage. Turn up and you are in the room.",
    },
    {
        "title": "Pick a team",
        "body": "Talk to the manager whose project you want. DBF, MATE ROV, Medical, SDC, and IAM3D take new members through the year, not only in the fall.",
    },
    {
        "title": "Get into G440",
        "body": "Safety and access training clears you for the shop. After that the tools, the printers, and the bench are yours to work on.",
    },
]

# Verified facts about ASME national, carried over from the About page.
ASME_FACTS = [
    {"value": "1880", "label": "ASME founded"},
    {"value": "100,000+", "label": "Members worldwide"},
    {"value": "140+", "label": "Countries"},
    {"value": "32,000", "label": "Student members"},
]

# Project File Structure

Each project follows this folder structure. The project root is referenced in each agent's TOOLS.md.

Agent workspace files (SOUL.md, IDENTITY.md, etc.) live separately in `~/.openclaw/agents/{agent_id}/workspace/`, not inside the project folder.

```
{PROJECT_NAME}/
├── ADMIN/                                         # Administrative and non-design files
│   ├── CORRESPONDENCE/                            # All written communication
│   │   └── TRANSMITTAL/                           # Formal record of files exchanged with external parties
│   │       ├── INCOMING/                          # Files received from external parties
│   │       │   ├── 00_CLIENT_{NAME}/
│   │       │   ├── 01_ARCH_{NAME}/
│   │       │   ├── 02_STRU_{NAME}/
│   │       │   ├── 03_ENERGY_{NAME}/
│   │       │   ├── 04_MEP_{NAME}/
│   │       │   ├── 05_CIVIL_{NAME}/
│   │       │   ├── 06_FACADE_{NAME}/
│   │       │   ├── 07_GREEN_BUILDING_{NAME}/
│   │       │   ├── 08_LANDSCAPE_{NAME}/
│   │       │   ├── 09_KITCHEN_{NAME}/
│   │       │   ├── 10_LIGHTING_{NAME}/
│   │       │   ├── 11_ACOUSTIC_{NAME}/
│   │       │   ├── 12_SITE_SURVEY_{NAME}/
│   │       │   ├── 13_QUANTITY_SURVEY_{NAME}/
│   │       │   ├── 14_INTERIOR_DESIGN_{NAME}/
│   │       │   ├── 15_CONTRACTOR_{NAME}/
│   │       │   ├── 16_WIND_TUNNEL_{NAME}/
│   │       │   ├── 17_LED_{NAME}/
│   │       │   └── 19_RENDERING_{NAME}/
│   │       └── OUTGOING/                          # Files sent to external parties (same subfolders as INCOMING)
│   └── PROJECT DATA/                              # Core project documentation
│       ├── CONTRACT/                              # Legal agreements and contracts
│       ├── DELIVERABLE LIST/                      # List of required deliverables
│       ├── DESIGN_NARRATIVE/                      # Written design intent and rationale
│       ├── MATERIAL_LIST/                         # Material selections and specifications
│       ├── PROGRAM/                               # Space program (room list, areas, adjacencies)
│       ├── PROJECT_CRITERIA/                      # Design criteria and constraints
│       ├── PROJECT_SCHEDULE/                      # Timeline, milestones, deadlines
│       └── ZONING_AND_CODES/                      # Zoning regulations and building codes
├── DESIGN/                                        # Production design files
│   ├── ANALYSIS/                                  # Environmental, structural, energy analysis
│   ├── CAD/                                       # 2D CAD drawings (AutoCAD, DWG)
│   ├── GIS/                                       # Geographic information system data
│   ├── REVIT/                                     # BIM models (Revit)
│   │   ├── Arch/                                  # Architectural Revit models
│   │   ├── Dynamo/                                # Dynamo visual programming scripts
│   │   ├── Export/                                # Exported files from Revit
│   │   ├── Families/                              # Custom Revit family components
│   │   ├── Links/                                 # Linked consultant models
│   │   └── ~Revit_Resource/                       # Revit templates and shared resources
│   └── RHINO/                                     # 3D design environment (Rhino)
│       ├── 00_CONTEXT/                            # Surrounding context models (neighboring buildings, streets)
│       ├── 01_SITE/                               # Site terrain, boundaries, existing conditions
│       ├── 02_BUILDING/                           # Building design models
│       ├── ~Composite_Models/                     # Combined/assembled models from multiple sources
│       ├── ~D5_Models/                            # Models prepared for D5 Render
│       ├── ~Grasshopper_Library/                  # Parametric definition scripts
│       ├── ~Physical_Models/                      # Files for physical model fabrication
│       ├── ~Reference_Models/                     # Reference geometry from other parties
│       ├── ~Rendering_Models/                     # Cleaned-up models prepared for rendering
│       └── ~Rhino_Setting/                        # Templates, display modes, shared settings
├── GRAPHIC/                                       # All visual output
│   ├── ANIMATIONS/                                # Video walkthroughs and flyovers
│   ├── DIAGRAMS/                                  # Concept diagrams, analysis graphics
│   ├── IMAGERY/                                   # Reference images, mood boards, site photos
│   ├── PRESENTATIONS/                             # Presentation decks
│   └── RENDERINGS/                                # Final rendered images
├── MANAGEMENT/                                    # Task assignments, deliverables, status tracking
└── STUDY/                                         # Per-agent private working folders
    ├── AGENT_{MANAGER}/                           # Manager's scratch work
    ├── AGENT_{DIRECTOR}/                          # Director's review comments
    ├── AGENT_{2D_DRAFTER}/                        # 2D drafter's work: drafts, iterations
    ├── AGENT_{3D_DRAFTER}/                        # 3D drafter's work: models, massing studies
    └── AGENT_{RENDERER}/                          # Renderer's work: render iterations, material boards
```

---

## Permissions

All agents share the same OS-level file access. Permissions are enforced through behavioral rules in each agent's SOUL.md.

| Agent | Read | Write |
|-------|------|-------|
| Manager | All folders | Own STUDY/, MANAGEMENT/, ADMIN/, DESIGN/, GRAPHIC/ (all public folders) |
| Director | All folders | Own STUDY/ only |
| 2D Drafter | All folders | Own STUDY/ only |
| 3D Drafter | All folders | Own STUDY/ only |
| Renderer | All folders | Own STUDY/ only |

- **All agents can read all folders** (public and all STUDY/ folders).
- **Only the manager writes to public folders.** The manager is the gatekeeper — all approved work flows through the manager to reach public folders.
- **Each agent writes only to their own STUDY/ folder.** No cross-writing between STUDY/ folders.

---

## Folder Naming Convention

All files must be saved in subfolders, never directly in a template folder root.

Subfolder format: `{YYYY.MM.DD}_{title}` (underscores, no spaces)

Examples:
- `MANAGEMENT/2026.03.11_residential_project/`
- `STUDY/AGENT_{DIRECTOR}/2026.03.11/jade_floor_plan_review.md`
- `INCOMING/00_CLIENT_{NAME}/2026.03.11_site_report/`

---

## Workflow

```
1. User sends input to Manager
   (could be a simple instruction, a detailed brief, or files/attachments)

2. Manager decomposes the input
   - Defines project scope, tasks, deliverables
   - Saves task files to MANAGEMENT/{date}_{title}/
   - If there are attachments, saves them to INCOMING/00_CLIENT_{NAME}/{date}_{title}/
   - Sends each agent a link to their task file + paths to source materials in public folders

3. Agents work in their own STUDY/ folders
   - Read source materials from public folders only
   - If extra material is needed → ask Manager
   - Manager provides path, or tells agent to pause until material is ready

4. Agent finishes → notifies Manager → Manager notifies Director

5. Director reviews work
   - Reads agent's work from agent's STUDY/ folder
   - Writes review comments in own STUDY/ folder (STUDY/AGENT_JACOB/)
   - Sends review file path to agent via message

6. Agent revises → loop back to step 5 until Director approves

7. Director approves → sends approved file paths to Manager

8. Manager copies approved files from agent's STUDY/ to appropriate public folder
   (e.g., GRAPHIC/RENDERINGS/{date}_{title}/)

9. Manager sends deliverable paths + submission checklist to User
```

> **Only the Manager knows the full file structure.** All other agents receive direct paths from the Manager and do not need to understand the folder hierarchy. The file structure is part of the Manager's TOOLS.md and skill set.

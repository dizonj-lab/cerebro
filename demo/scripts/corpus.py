"""The CEREBRO demo corpus: sixteen illustrative documents across two projects, written so that their relationships
are stated in the text itself (every authored link carries the sentence that evidences it).

All documents are fictional samples for the demo. Figures quoted from MealSenseAI's EXP-002 evaluation are the
developer-reported values from that project's MODEL_AND_LIMITATIONS document; nothing else is a measurement.
"""

OWNER = "Joselito Dizon"

# id, file type, title, short name used in other documents' text, date, kind, project, authors, summary, sections
ARTIFACTS = [
    dict(id="ART-0001", type="pdf", title="NUS-ISS Practice Module Brief: Intelligent Reasoning Systems", short="Practice Module Brief",
         date="2026-07-06", kind="Brief", project="Coursework", authors=["NUS-ISS teaching team"],
         summary="Course brief for the Intelligent Reasoning Systems practice module: a group-built reasoning system with a report, a runnable demo and a short video.",
         sections=[
             ("Purpose", [
                 "The practice module asks each group to design and build an intelligent reasoning system that solves a real problem for a real user.",
                 "Systems should combine at least two reasoning techniques, such as knowledge representation, search, machine learning or retrieval, and explain how they work together."]),
             ("Deliverables", [
                 "Each group submits a project report, a runnable demo web app and a recorded video of no more than ten minutes.",
                 "The runnable demo must start with documented commands on a clean machine, and markers must be able to explore it without private credentials.",
                 "Provenance matters: every answer a system gives should be traceable back to the evidence it used."]),
             ("Assessment", [
                 "Marks are awarded for problem framing, technical depth, the quality of the reasoning, evaluation against ground truth, and the clarity of the demo.",
                 "Groups are encouraged to keep architecture decisions in a written log and to show how evaluation shaped the design."]),
         ]),
    dict(id="ART-0002", type="docx", title="CEREBRO Vision and Concept Note", short="Vision and Concept Note",
         date="2026-07-14", kind="Concept note", project="CEREBRO", authors=[OWNER],
         summary="Why CEREBRO exists: a private digital twin of personal knowledge that learns, connects, reasons and recalls, always with provenance.",
         sections=[
             ("The problem", [
                 "Personal knowledge is scattered across PDFs, notes, slides and messages, and the links between them live only in our heads.",
                 "When we need to recall why a decision was made, the evidence is rarely where we expect it."]),
             ("The idea", [
                 "CEREBRO is an Adaptive Knowledge and Reasoning Digital Twin: a private store that turns documents into connected knowledge fragments.",
                 "It follows four pillars: Learn from new artifacts, Connect them into a knowledge graph, Reason over that graph, and Recall answers with their sources.",
                 "This concept note responds to the Practice Module Brief, which asks for a reasoning system whose answers are traceable to evidence."]),
             ("Principles", [
                 "Provenance first: every fragment keeps a pointer to its source artifact, page and character range.",
                 "Private by default: processing runs locally, and any cloud model requires explicit consent.",
                 "Human in the loop: AI-suggested metadata is reviewed and approved before an artifact is registered."]),
         ]),
    dict(id="ART-0003", type="pdf", title="CEREBRO Solution Architecture", short="CEREBRO Solution Architecture",
         date="2026-08-02", kind="Architecture", project="CEREBRO", authors=[OWNER],
         summary="Containers, data stores and the staged plan from authentication to knowledge graph, reasoning and visualisation.",
         sections=[
             ("Context", [
                 "This architecture extends the Vision and Concept Note into a buildable system.",
                 "It applies the retrieval and graph patterns covered in the Knowledge Graphs and RAG lecture notes."]),
             ("Containers", [
                 "The web tier is Next.js with React; the API is FastAPI with SQLAlchemy; PostgreSQL holds users, artifacts and fragments.",
                 "React never connects to PostgreSQL directly: all data access goes through the API, and the web pod proxies requests under one origin.",
                 "Later stages add an object store for originals, a vector store for embeddings, a graph store for entities and relationships, and a local LLM served by Ollama."]),
             ("Pipeline", [
                 "An artifact moves through upload, file inspection, metadata extraction, AI enrichment, human review and registration.",
                 "Registered artifacts are segmented into knowledge fragments, each carrying concepts, entities, temporal fields and provenance.",
                 "Every pipeline step emits telemetry so the user can see which stage is running and how long it took."]),
             ("Deployment", [
                 "Kubernetes in a dedicated cerebro namespace is the primary target, with Docker Compose as the simpler fallback.",
                 "Host ports are configurable because ports 3000, 8000 and 5432 are often taken on a shared machine."]),
         ]),
    dict(id="ART-0004", type="pdf", title="Lecture Notes: Knowledge Graphs and Retrieval-Augmented Generation", short="Knowledge Graphs and RAG lecture notes",
         date="2026-07-21", kind="Lecture notes", project="Coursework", authors=[OWNER],
         summary="Notes on entity and relationship extraction, graph stores, embeddings, hybrid retrieval and grounding LLM answers in cited evidence.",
         sections=[
             ("Knowledge graphs", [
                 "A knowledge graph stores entities as nodes and typed relationships as edges, which makes multi-hop questions answerable.",
                 "Typical relationship types in a document graph include cites, extends, implements, evaluates and supersedes."]),
             ("Retrieval-augmented generation", [
                 "Retrieval-augmented generation first retrieves relevant passages, then asks a language model to answer using only those passages.",
                 "Hybrid retrieval combines keyword scoring such as BM25 with embedding similarity, which helps with both exact terms and paraphrases.",
                 "Grounding means every claim in the answer can be traced to a retrieved passage; unsupported claims should be rejected, not hidden."]),
             ("Evaluation", [
                 "Retrieval quality is measured against a labelled ground truth, for example recall at k and the rate of unsupported claims.",
                 "Small local models can phrase answers well, but the facts must come from the retrieved evidence."]),
         ]),
    dict(id="ART-0005", type="pdf", title="CEREBRO Ground Truth Benchmark (CEREBRO-GT v0.1)", short="Ground Truth Benchmark",
         date="2026-09-05", kind="Benchmark", project="CEREBRO", authors=[OWNER],
         summary="A frozen, annotated benchmark for measuring the knowledge pipeline: expected fragments, concepts and provenance for each source.",
         sections=[
             ("Why a benchmark", [
                 "The Practice Module Brief rewards evaluation against ground truth, so the pipeline needs a fixed reference before it is tuned.",
                 "This benchmark evaluates the pipeline described in the CEREBRO Solution Architecture."]),
             ("Annotation schema", [
                 "Each benchmark item records the source artifact, its checksum, the expected fragments with character ranges, and the expected concepts.",
                 "Annotations are frozen as version 0.1 and persisted with their own checksum, so later changes are visible."]),
             ("Acceptance tests", [
                 "A pipeline run passes when every expected fragment is produced with the right source location and no fragment lacks provenance.",
                 "Concept extraction is scored separately, because wording can differ while meaning is preserved."]),
         ]),
    dict(id="ART-0006", type="docx", title="Knowledge Pipeline Proof of Concept: Results", short="Knowledge Pipeline PoC",
         date="2026-09-24", kind="Results", project="CEREBRO", authors=[OWNER],
         summary="Steps 01 to 06 of the knowledge pipeline proof of concept, from ground truth to an integrated knowledge experience.",
         sections=[
             ("Scope", [
                 "This proof of concept implements the pipeline from the CEREBRO Solution Architecture in notebooks before it moves into the product.",
                 "Results are measured against the Ground Truth Benchmark."]),
             ("What was built", [
                 "Step 02 inspects uploaded files, extracts deterministic metadata and asks a local model to suggest titles, topics and tags.",
                 "A human review step approves or corrects the AI suggestions before the artifact is registered.",
                 "Step 03 segments the text into knowledge fragments using deterministic sentence segmentation, each with a character range.",
                 "Step 05 adds embedding similarity so related fragments across documents can be connected."]),
             ("Findings", [
                 "Deterministic segmentation reproduced every expected fragment and its source location in the benchmark.",
                 "AI enrichment was useful for topics and tags but needed human review for titles and people.",
                 "The decision to keep human review mandatory was recorded in the Group 7 meeting minutes."]),
         ]),
    dict(id="ART-0007", type="docx", title="Meeting Minutes: Group 7, 12 September 2026", short="Group 7 meeting minutes",
         date="2026-09-12", kind="Minutes", project="CEREBRO", authors=[OWNER],
         summary="Decisions on the benchmark, mandatory human review, and reusing the pipeline telemetry pattern across projects.",
         sections=[
             ("Attendees", ["Joselito Dizon (minutes) and Group 7 members."]),
             ("Decisions", [
                 "The group agreed to freeze the Ground Truth Benchmark as version 0.1 before tuning the Knowledge Pipeline PoC.",
                 "Human review of AI-suggested metadata stays mandatory; no artifact is registered on AI output alone.",
                 "The pipeline telemetry pattern from the CEREBRO Solution Architecture will also be reused in MealSenseAI's analysis drawer."]),
             ("Actions", [
                 "Joselito to write up the PoC results and prepare the runnable demo required by the Practice Module Brief.",
                 "Check that the home server can host both projects; see the Buddy runbook."]),
         ]),
    dict(id="ART-0008", type="pdf", title="MealSenseAI Project Proposal", short="MealSenseAI Project Proposal",
         date="2026-06-20", kind="Proposal", project="MealSenseAI", authors=[OWNER],
         summary="A photo-based meal logger that recognises foods, estimates nutrition and explains its confidence, aimed at people managing their diet.",
         sections=[
             ("Problem", [
                 "Logging meals by hand is tedious, and people managing diabetes or weight need nutrition estimates they can trust and understand.",
                 "Local dishes in Singapore are poorly covered by generic food apps."]),
             ("Proposed solution", [
                 "MealSenseAI recognises foods from a photo, segments multi-food plates, estimates portions and nutrients, and explains each result.",
                 "Recognition is trained on Food-101 and FoodSG-233; see the Food-101 dataset notes and the FoodSG-233 dataset notes.",
                 "A grounded Meal Advisor answers questions using only the user's meals, the food table and approved guidance."]),
             ("Safety", [
                 "The app never gives medication or insulin advice, and every estimate is labelled as an estimate.",
                 "Health information is used only with explicit consent."]),
         ]),
    dict(id="ART-0009", type="docx", title="MealSenseAI Solution Architecture", short="MealSenseAI Solution Architecture",
         date="2026-07-10", kind="Architecture", project="MealSenseAI", authors=[OWNER],
         summary="FastAPI, React and PostgreSQL around an ONNX food classifier, YOLO11n-seg plate segmentation and an optional local LLM.",
         sections=[
             ("Overview", [
                 "This architecture implements the MealSenseAI Project Proposal as a FastAPI backend, a React frontend and PostgreSQL.",
                 "The food classifier is the EXP-002 model exported to ONNX; plates with several foods are split with YOLO11n-seg."]),
             ("Grounded advisor", [
                 "The Meal Advisor drafts every answer from evidence: the user's data, raw model scores, the food table and approved guidance.",
                 "An optional local model served by Ollama may rephrase the draft, but a validator rejects any new number or food it introduces.",
                 "This follows the grounding approach in the Knowledge Graphs and RAG lecture notes."]),
             ("Explainability", [
                 "An analysis drawer shows each pipeline stage with progress and timing, reusing the telemetry pattern from the CEREBRO Solution Architecture.",
                 "Model accuracy and limitations are documented in the EXP-002 Model Evaluation Report."]),
         ]),
    dict(id="ART-0010", type="pdf", title="Dataset Notes: Food-101", short="Food-101 dataset notes",
         date="2026-06-15", kind="Dataset notes", project="MealSenseAI", authors=[OWNER],
         summary="Reading notes on Food-101 (Bossard, Guillaumin and Van Gool, ECCV 2014): 101 classes, 101,000 images.",
         sections=[
             ("Citation", ["Bossard, L., Guillaumin, M. and Van Gool, L. Food-101: Mining Discriminative Components with Random Forests. ECCV 2014."]),
             ("Contents", [
                 "Food-101 has 101 food categories with 1,000 images each: 750 for training and 250 for testing.",
                 "The training images were deliberately left uncleaned, so some label noise is expected."]),
             ("Use in MealSenseAI", [
                 "Food-101 provides broad international coverage, but few Singapore hawker dishes, which is why FoodSG-233 is added.",
                 "Licence and citation requirements are recorded on the MealSenseAI About page."]),
         ]),
    dict(id="ART-0011", type="docx", title="Dataset Notes: FoodSG-233", short="FoodSG-233 dataset notes",
         date="2026-06-16", kind="Dataset notes", project="MealSenseAI", authors=[OWNER],
         summary="Reading notes on FoodSG-233, a dataset of 233 local Singapore dishes, and how it complements Food-101.",
         sections=[
             ("Contents", [
                 "FoodSG-233 covers 233 dishes commonly eaten in Singapore, including hawker favourites such as chicken rice, laksa and nasi lemak.",
                 "It complements the Food-101 dataset notes by filling the local-cuisine gap."]),
             ("Use in MealSenseAI", [
                 "Classes from both datasets are merged into one taxonomy and mapped to nutrition records.",
                 "The dataset owners are credited on the About page, as required by the MealSenseAI Project Proposal."]),
         ]),
    dict(id="ART-0012", type="pdf", title="EXP-002 Model Evaluation Report", short="EXP-002 Model Evaluation Report",
         date="2026-08-18", kind="Evaluation", project="MealSenseAI", authors=[OWNER],
         summary="Developer-reported accuracy of the EXP-002 food classifier and the ONNX runtime parity check.",
         sections=[
             ("Model", [
                 "EXP-002 is the food classifier used in the MealSenseAI Solution Architecture, trained on the merged Food-101 and FoodSG-233 taxonomy."]),
             ("Results", [
                 "Developer-reported results are 70.63% top-1 accuracy, 85.66% top-3 accuracy and 66.68% macro-F1.",
                 "Roughly three in ten photos get a wrong top-1 class, which is why the app always shows alternatives and asks the user to confirm."]),
             ("Runtime parity", [
                 "The ONNX export was checked against PyTorch on 601 images: top-1 and top-3 agreement was 100%.",
                 "Parity shows the runtime reproduces the checkpoint; it is not an accuracy measurement."]),
         ]),
    dict(id="ART-0013", type="docx", title="Design Memo: Glucose Estimates in mmol/L", short="Glucose estimate design memo",
         date="2026-10-24", kind="Design memo", project="MealSenseAI", authors=[OWNER],
         summary="Replacing the relative glucose index with mmol/L: pre-meal reading plus an estimated rise, a wide band, and personal calibration.",
         sections=[
             ("Decision", [
                 "The forecast chart will show glucose in mmol/L as the user's pre-meal reading plus the estimated rise from the meal.",
                 "This memo extends the MealSenseAI Solution Architecture, which previously showed only a relative index."]),
             ("Calibration", [
                 "Without readings, the rise is anchored to typical glucose tolerance test responses, with a band of plus or minus fifty percent.",
                 "After three meals with readings before and after eating, the estimate is calibrated to the user's own response.",
                 "Glycaemic index and load assumptions follow the glycaemic index and load guidance notes."]),
             ("Safety", [
                 "The curve is always labelled an estimate, even when it starts from a measured reading, and it must never be used to adjust insulin or medication."]),
         ]),
    dict(id="ART-0014", type="pdf", title="Guidance Notes: Glycaemic Index and Glycaemic Load", short="glycaemic index and load guidance notes",
         date="2026-07-30", kind="Guidance notes", project="MealSenseAI", authors=[OWNER],
         summary="Educational notes on glycaemic index and load, drawn from the international GI tables and diabetes care standards.",
         sections=[
             ("Definitions", [
                 "Glycaemic index ranks carbohydrate foods by how quickly they raise blood glucose compared with a reference.",
                 "Glycaemic load multiplies the index by the grams of available carbohydrate in a portion, so portion size matters."]),
             ("Sources", [
                 "Values come from the international tables of glycaemic index and glycaemic load values (Atkinson and colleagues, 2021).",
                 "General dietary guidance follows the American Diabetes Association Standards of Care."]),
             ("Use in MealSenseAI", [
                 "Foods without a published index use an assumed value, and the app says so.",
                 "These notes inform the forecast described in the MealSenseAI Solution Architecture."]),
         ]),
    dict(id="ART-0015", type="docx", title="Home Server Runbook: Buddy", short="Buddy runbook",
         date="2026-10-05", kind="Runbook", project="Infrastructure", authors=[OWNER],
         summary="How the Ubuntu home server hosts MealSenseAI and CEREBRO with Docker Compose, an NVIDIA GPU, Ollama and a Cloudflare Tunnel.",
         sections=[
             ("Host", [
                 "Buddy is an Ubuntu server with an NVIDIA GPU, running Docker Compose and Ollama.",
                 "Public access goes through a Cloudflare Tunnel, so no router ports are opened."]),
             ("Services", [
                 "MealSenseAI runs as backend, frontend, PostgreSQL and Redis containers, deployed as described in the MealSenseAI Solution Architecture.",
                 "CEREBRO runs as a separate Compose project on its own port, following the deployment section of the CEREBRO Solution Architecture.",
                 "Both projects share the local Ollama service, sized according to the Local LLM Evaluation Plan."]),
             ("Rules", [
                 "Never run destructive volume-removal commands, and back up each database before a deployment.",
                 "Deploy only after explicit approval, and keep a rollback commit for every release."]),
         ]),
    dict(id="ART-0016", type="pdf", title="Local LLM Evaluation Plan", short="Local LLM Evaluation Plan",
         date="2026-09-28", kind="Plan", project="Infrastructure", authors=[OWNER],
         summary="How small local models will be compared for grounded answering in both projects; measurements are still to be run on Buddy.",
         sections=[
             ("Goal", [
                 "Choose a local model for answer phrasing in the MealSenseAI Meal Advisor and for the reasoning stage in the CEREBRO Solution Architecture.",
                 "No external LLM API is used; every candidate runs on Buddy through Ollama."]),
             ("Method", [
                 "Each candidate phrases answers over a labelled set; a validator counts unsupported numbers and entities, following the Knowledge Graphs and RAG lecture notes.",
                 "Latency, tokens per second and GPU memory will be measured on the server, not estimated."]),
             ("Status", [
                 "The labelled sets exist; the measurements on Buddy have not been run yet, so no results are reported here."]),
         ]),
]

# source -> target, type, evidence = the short name of the target as it appears in the source text
LINKS = [
    ("ART-0002", "ART-0001", "responds to"),
    ("ART-0003", "ART-0002", "extends"),
    ("ART-0003", "ART-0004", "applies"),
    ("ART-0005", "ART-0001", "responds to"),
    ("ART-0005", "ART-0003", "evaluates"),
    ("ART-0006", "ART-0003", "implements"),
    ("ART-0006", "ART-0005", "measured against"),
    ("ART-0006", "ART-0007", "decision recorded in"),
    ("ART-0007", "ART-0005", "decides on"),
    ("ART-0007", "ART-0003", "reuses pattern from"),
    ("ART-0007", "ART-0001", "actions for"),
    ("ART-0007", "ART-0015", "refers to"),
    ("ART-0008", "ART-0010", "cites"),
    ("ART-0008", "ART-0011", "cites"),
    ("ART-0009", "ART-0008", "implements"),
    ("ART-0009", "ART-0004", "applies"),
    ("ART-0009", "ART-0003", "reuses pattern from"),
    ("ART-0009", "ART-0012", "documented in"),
    ("ART-0011", "ART-0010", "complements"),
    ("ART-0011", "ART-0008", "required by"),
    ("ART-0012", "ART-0009", "evaluates"),
    ("ART-0013", "ART-0009", "extends"),
    ("ART-0013", "ART-0014", "cites"),
    ("ART-0014", "ART-0009", "informs"),
    ("ART-0015", "ART-0009", "deploys"),
    ("ART-0015", "ART-0003", "deploys"),
    ("ART-0015", "ART-0016", "sized by"),
    ("ART-0016", "ART-0003", "informs"),
    ("ART-0016", "ART-0004", "applies"),
]

# concept -> keywords (lower-case substrings); entities -> (kind, keywords)
CONCEPTS = {
    "Provenance": ["provenance", "traceable", "source location", "character range", "checksum"],
    "Knowledge graph": ["knowledge graph", "graph store", "relationship"],
    "Retrieval-augmented generation": ["retrieval", "rag", "retrieved"],
    "Grounding": ["grounded", "grounding", "unsupported", "validator", "evidence"],
    "Embeddings": ["embedding", "vector store"],
    "Human review": ["human review", "human in the loop", "reviewed and approved", "approves or corrects"],
    "Ground truth evaluation": ["ground truth", "benchmark", "labelled set", "labelled ground", "acceptance test"],
    "Knowledge fragments": ["fragment"],
    "Pipeline telemetry": ["telemetry", "pipeline stage", "progress and timing"],
    "Food recognition": ["recognis", "classifier", "food categories", "top-1"],
    "Nutrition estimation": ["nutrition", "nutrient", "portion"],
    "Glycaemic index": ["glycaemic", "glucose"],
    "Safety and consent": ["consent", "insulin", "medication", "safety"],
    "Local LLM": ["ollama", "local model", "language model", "llm"],
    "Deployment": ["docker", "kubernetes", "compose", "deploy", "cloudflare", "host ports", "server"],
    "Privacy": ["private", "privacy", "locally", "no external"],
}
ENTITIES = {
    "Joselito Dizon": ("person", ["joselito"]),
    "NUS-ISS": ("organisation", ["nus-iss"]),
    "Group 7": ("organisation", ["group 7"]),
    "CEREBRO": ("project", ["cerebro"]),
    "MealSenseAI": ("project", ["mealsenseai", "meal advisor"]),
    "Food-101": ("dataset", ["food-101"]),
    "FoodSG-233": ("dataset", ["foodsg-233"]),
    "EXP-002": ("model", ["exp-002"]),
    "YOLO11n-seg": ("model", ["yolo11n-seg"]),
    "Ollama": ("tool", ["ollama"]),
    "PostgreSQL": ("tool", ["postgresql"]),
    "FastAPI": ("tool", ["fastapi"]),
    "Buddy (home server)": ("system", ["buddy"]),
    "Cloudflare Tunnel": ("tool", ["cloudflare"]),
}

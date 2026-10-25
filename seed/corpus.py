"""The CEREBRO demo library: twenty-two related artefacts, written to exercise every part of the product.

Why it is shaped this way:

* **One topic vocabulary.** Every document's topics come from TOPICS and appear verbatim in its text, so the
  Galaxy's co-occurrence edges recur (two or more documents) instead of each file inventing its own words.
* **Shared entities.** Organisations, projects and technologies recur across documents, so the entity layer joins
  topics from both projects. The owner is the author of most documents and is recorded as author, not as a "people"
  entity: a person linked to every topic would sit at the centre of the Galaxy and say nothing.
* **Stated dates.** Each document says when things happened ("On 12 September 2026 …"), which is what the
  Timeline reads. No other number between 1900 and 2099 appears in the text, so nothing else is mistaken for a
  year. Publication years of cited work are left out too, so the Timeline spans the months the work happened.
* **Honest metadata.** created_date is written into each file's own metadata; an author is either in the file's
  metadata or printed as a "Presented by" byline; lecture decks have no author, and stay unknown.

All documents are illustrative samples for the demo. The only real figures are MealSenseAI's developer-reported
EXP-002 results, quoted with that label.
"""

OWNER = "Joselito Dizon"

TOPICS = [
    "Knowledge Graphs", "Retrieval-Augmented Generation", "Semantic Search", "Provenance", "Human-in-the-Loop Review",
    "Food Recognition", "Nutrition Estimation", "Glycaemic Response", "Local Language Models", "Model Evaluation",
    "Containerised Deployment", "Explainable AI",
]

# kind: pdf | docx | pptx | md. body: list of (heading, [paragraphs]) — for pptx each pair is one slide with bullets.
DOCS = [
    dict(file="01-reading-notes-food-datasets.pdf", kind="pdf", date="2026-06-15", author=OWNER,
         title="Reading Notes: Food-101 and FoodSG-233",
         description="What the two food image datasets contain, where they fall short, and how MealSenseAI combines them.",
         topics=["Food Recognition", "Model Evaluation"], projects=["MealSenseAI"], technologies=[], organizations=[], people=[],
         tags=["datasets", "computer vision"],
         body=[
             ("Why these datasets", [
                 "These notes were written on 15 June 2026 while scoping Food Recognition for MealSenseAI. A photo-based meal "
                 "logger is only as good as the dishes its classifier has seen, so the choice of training data comes first.",
             ]),
             ("Food-101", [
                 "Food-101 was published by Bossard, Guillaumin and Van Gool at the European Conference on Computer Vision. It contains one hundred and one "
                 "food categories with a thousand images each: seven hundred and fifty for training and two hundred and fifty "
                 "for testing. The training images were deliberately left uncleaned, so some label noise is expected and "
                 "Model Evaluation should rely on the cleaner test split.",
                 "Its coverage is international: pizza, sushi, steak, ramen. Singapore hawker dishes are almost absent, which "
                 "matters for a local audience.",
             ]),
             ("FoodSG-233", [
                 "FoodSG-233 covers two hundred and thirty-three dishes commonly eaten in Singapore, including chicken rice, "
                 "laksa, nasi lemak and kaya toast. It fills exactly the gap that Food-101 leaves.",
                 "Combining both datasets gives a merged taxonomy that is broad and local at the same time. The cost is class "
                 "imbalance, so Model Evaluation must report macro-F1 alongside top-1 accuracy, not accuracy alone.",
             ]),
         ]),
    dict(file="02-mealsenseai-project-proposal.pdf", kind="pdf", date="2026-06-20", author=OWNER,
         title="MealSenseAI Project Proposal",
         description="A photo-based meal logger that recognises foods, estimates nutrition and explains every result.",
         topics=["Food Recognition", "Nutrition Estimation", "Glycaemic Response", "Explainable AI"], projects=["MealSenseAI"],
         technologies=[], organizations=["Health Promotion Board"], people=[], tags=["proposal", "health"],
         body=[
             ("Problem", [
                 "Logging meals by hand is tedious, and people managing diabetes or their weight need numbers they can trust "
                 "and understand. This proposal was submitted on 20 June 2026.",
                 "Generic food apps rarely recognise local dishes and rarely say how sure they are.",
             ]),
             ("Proposed solution", [
                 "MealSenseAI takes a photo, performs Food Recognition on each item on the plate, and turns portions into "
                 "Nutrition Estimation: calories, carbohydrate, protein, fat, fibre and sodium. Every estimate is shown with "
                 "its confidence and the alternatives the model considered, which is the Explainable AI requirement.",
                 "For users who manage their blood sugar, the app adds an educational view of Glycaemic Response: how a meal's "
                 "carbohydrate and glycaemic load might affect glucose after eating.",
             ]),
             ("Safety", [
                 "The app never gives medication or insulin advice, labels every estimate as an estimate, and uses health "
                 "information only with explicit consent. Dietary guidance follows the Health Promotion Board's My Healthy Plate.",
             ]),
         ]),
    dict(file="03-irs-practice-module-brief.pdf", kind="pdf", date="2026-07-06", author="NUS-ISS teaching team",
         title="Intelligent Reasoning Systems: Practice Module Brief",
         description="What each group must build and submit, and how it will be assessed.",
         topics=["Explainable AI", "Model Evaluation", "Provenance"], projects=[], technologies=[], organizations=["NUS-ISS"],
         people=[], tags=["coursework", "assessment"],
         body=[
             ("Purpose", [
                 "The NUS-ISS practice module starts on 6 July 2026. Each group designs and builds an intelligent reasoning system "
                 "that solves a real problem for a real user, combining at least two reasoning techniques.",
             ]),
             ("Deliverables", [
                 "Groups submit a report, a runnable demo and a short video by 30 November 2026. The demo must start with "
                 "documented commands on a clean machine.",
                 "Every answer a system gives should carry its Provenance: markers must be able to trace an output back to "
                 "the evidence it used. Systems are expected to practise Explainable AI, not merely produce outputs.",
             ]),
             ("Assessment", [
                 "Marks reward problem framing, technical depth, the quality of the reasoning and Model Evaluation against a "
                 "ground truth. A mid-term presentation in October 2026 checks progress.",
             ]),
         ]),
    dict(file="04-lecture-knowledge-graphs.pptx", kind="pptx", date="2026-07-08", author=None,
         title="Lecture 3: Knowledge Representation and Knowledge Graphs",
         description="Lecture deck on representing knowledge as entities and relationships, and keeping its sources.",
         topics=["Knowledge Graphs", "Provenance", "Explainable AI"], projects=[], technologies=[], organizations=["NUS-ISS"],
         people=[], tags=["lecture"],
         body=[
             ("Knowledge Representation and Knowledge Graphs", ["Intelligent Reasoning Systems, lecture 3, 8 July 2026", "NUS-ISS"]),
             ("What a knowledge graph is", [
                 "Knowledge Graphs store entities as nodes and typed relationships as edges",
                 "Multi-hop questions become graph traversals",
                 "Typical relations in a document graph: cites, extends, implements, evaluates"]),
             ("Where the facts come from", [
                 "Every node and edge should keep its Provenance: the source document and location",
                 "A relationship without a source is an assertion, not knowledge",
                 "Co-occurrence is evidence of association, not of meaning"]),
             ("Why it matters for reasoning", [
                 "Explainable AI needs paths a person can follow",
                 "A graph lets a system show why two ideas are connected",
                 "Exercise: model your own notes as a small graph"]),
         ]),
    dict(file="05-cerebro-vision-concept-note.docx", kind="docx", date="2026-07-14", author=OWNER,
         title="CEREBRO Vision and Concept Note",
         description="Why CEREBRO exists: a private digital twin of personal knowledge that learns, connects, reasons and recalls.",
         topics=["Knowledge Graphs", "Provenance", "Human-in-the-Loop Review", "Semantic Search"], projects=["CEREBRO"],
         technologies=[], organizations=["NUS-ISS"], people=[], tags=["vision"],
         body=[
             ("The problem", [
                 "People accumulate knowledge well and recall its details badly. Lecture decks, papers, proposals and notes pile "
                 "up, and the links between them live only in our heads. This note was written on 14 July 2026 in response to "
                 "the NUS-ISS practice module brief.",
             ]),
             ("The idea", [
                 "CEREBRO is an Adaptive Knowledge and Reasoning Digital Twin. It learns from documents, connects them into "
                 "Knowledge Graphs of topics and entities, and recalls answers with citations.",
                 "Semantic Search lets a person ask in their own words rather than guess the exact phrase a document used.",
             ]),
             ("Principles", [
                 "Provenance first: every fragment keeps its source document, page and character range.",
                 "Human-in-the-Loop Review: enrichment proposes metadata, and only the owner's approval lets a document into "
                 "retrieval.",
                 "Private by default: processing stays in the CEREBRO environment, with no cloud AI.",
             ]),
         ]),
    dict(file="06-lecture-retrieval-augmented-generation.pptx", kind="pptx", date="2026-07-21", author=None,
         title="Lecture 5: Retrieval-Augmented Generation",
         description="Lecture deck on retrieving evidence first and generating answers only from it.",
         topics=["Retrieval-Augmented Generation", "Semantic Search", "Local Language Models", "Model Evaluation"],
         projects=[], technologies=["Ollama"], organizations=["NUS-ISS"], people=[], tags=["lecture"],
         body=[
             ("Retrieval-Augmented Generation", ["Intelligent Reasoning Systems, lecture 5, 21 July 2026", "NUS-ISS"]),
             ("Retrieve, then generate", [
                 "Retrieval-Augmented Generation first finds relevant passages",
                 "The model answers using only those passages, and cites them",
                 "If retrieval finds nothing, the right answer is to say so"]),
             ("Finding the passages", [
                 "Keyword search (BM25, full-text) matches exact terms",
                 "Semantic Search with embeddings matches meaning and paraphrase",
                 "Hybrid retrieval fuses both, for example with reciprocal rank fusion"]),
             ("Running it privately", [
                 "Local Language Models served by Ollama keep documents on your own machine",
                 "Small models phrase well; facts must still come from the passages"]),
             ("Measuring it", [
                 "Model Evaluation for RAG: recall at k, citation accuracy, unsupported-claim rate",
                 "Build a labelled ground truth before tuning anything"]),
         ]),
    dict(file="07-mealsenseai-solution-architecture.docx", kind="docx", date="2026-07-10", author=OWNER,
         title="MealSenseAI Solution Architecture",
         description="FastAPI, React and PostgreSQL around an ONNX food classifier, plate segmentation and an optional local model.",
         topics=["Food Recognition", "Nutrition Estimation", "Local Language Models", "Containerised Deployment", "Explainable AI"],
         projects=["MealSenseAI"], technologies=["FastAPI", "PostgreSQL", "ONNX Runtime", "YOLO11n-seg", "Ollama", "Docker Compose"],
         organizations=[], people=[], tags=["architecture"],
         body=[
             ("Overview", [
                 "This architecture, agreed on 10 July 2026, implements the MealSenseAI proposal as a FastAPI backend, a React "
                 "frontend and PostgreSQL.",
                 "Food Recognition uses the EXP-002 classifier exported to ONNX Runtime; plates with several foods are split "
                 "with YOLO11n-seg before each region is classified.",
             ]),
             ("From pixels to nutrients", [
                 "Each recognised food is matched to a nutrition record and scaled by its estimated portion. Nutrition "
                 "Estimation keeps unknown values blank rather than guessing them.",
                 "An analysis drawer shows every pipeline stage with its timing: the Explainable AI view.",
             ]),
             ("Meal Advisor", [
                 "A Meal Advisor answers questions from the user's own meals and the food table. Local Language Models served "
                 "by Ollama may rephrase a drafted answer, but a validator rejects any number or food the model adds.",
             ]),
             ("Deployment", [
                 "Containerised Deployment with Docker Compose runs the backend, frontend, PostgreSQL and Redis together, with "
                 "an optional GPU override for inference.",
             ]),
         ]),
    dict(file="08-guidance-glycaemic-index-and-load.pdf", kind="pdf", date="2026-07-30", author=OWNER,
         title="Guidance Notes: Glycaemic Index and Glycaemic Load",
         description="Educational notes on glycaemic index and load, and how they inform MealSenseAI's estimates.",
         topics=["Glycaemic Response", "Nutrition Estimation"], projects=["MealSenseAI"], technologies=[],
         organizations=["American Diabetes Association", "World Health Organization"], people=[], tags=["health", "guidance"],
         body=[
             ("Definitions", [
                 "These notes were compiled on 30 July 2026. Glycaemic index ranks carbohydrate foods by how quickly they raise "
                 "blood glucose compared with a reference food. Glycaemic load multiplies the index by the grams of available "
                 "carbohydrate in a portion, so portion size matters as much as the food.",
             ]),
             ("Sources", [
                 "Index values come from the international tables of glycaemic index and load published by Atkinson and colleagues. General "
                 "guidance follows the American Diabetes Association Standards of Care, and the World Health Organization's "
                 "advice on free sugars and fibre.",
             ]),
             ("Use in MealSenseAI", [
                 "Glycaemic Response in the app is educational. Nutrition Estimation supplies the carbohydrate; foods without a "
                 "published index use an assumed value, and the app says so. Nothing here is advice on medication.",
             ]),
         ]),
    dict(file="09-cerebro-solution-architecture.pdf", kind="pdf", date="2026-08-02", author=OWNER,
         title="CEREBRO Solution Architecture",
         description="Containers, data stores and the pipeline from upload to an answer with citations.",
         topics=["Knowledge Graphs", "Retrieval-Augmented Generation", "Semantic Search", "Provenance", "Containerised Deployment"],
         projects=["CEREBRO"], technologies=["Next.js", "FastAPI", "PostgreSQL", "Ollama", "Kubernetes", "Docker Compose"],
         organizations=[], people=[], tags=["architecture"],
         body=[
             ("Context", [
                 "This architecture was baselined on 2 August 2026. It turns the vision note into a buildable system and applies "
                 "the patterns from the lectures on Knowledge Graphs and Retrieval-Augmented Generation.",
             ]),
             ("Containers", [
                 "The web tier is Next.js; the API is FastAPI; PostgreSQL holds users, artefacts, fragments and their vectors. "
                 "The browser only calls the web origin, which proxies the API, so the session cookie stays first-party.",
             ]),
             ("Pipeline", [
                 "An artefact moves through upload, inspection, extraction, review and approval. Approval re-verifies the "
                 "checksum, splits the text into fragments and embeds them for Semantic Search. Each fragment records its "
                 "Provenance: document, page and character range.",
                 "Recall retrieves passages first and lets a local model served by Ollama phrase the answer, with citations.",
             ]),
             ("Deployment", [
                 "Containerised Deployment targets Kubernetes in a cerebro namespace, with Docker Compose as the simpler path. "
                 "Host ports are configurable because a shared machine often has its usual ports taken.",
             ]),
         ]),
    dict(file="10-exp-002-model-evaluation-report.pdf", kind="pdf", date="2026-08-18", author=OWNER,
         title="EXP-002 Model Evaluation Report",
         description="Developer-reported accuracy of the EXP-002 food classifier and the ONNX runtime parity check.",
         topics=["Food Recognition", "Model Evaluation", "Explainable AI"], projects=["MealSenseAI"],
         technologies=["ONNX Runtime"], organizations=[], people=[], tags=["evaluation"],
         body=[
             ("Model", [
                 "This report was issued on 18 August 2026. EXP-002 is the Food Recognition model used by MealSenseAI, trained "
                 "on the merged Food-101 and FoodSG-233 taxonomy.",
             ]),
             ("Results", [
                 "Developer-reported results are 70.63% top-1 accuracy, 85.66% top-3 accuracy and 66.68% macro-F1.",
                 "Roughly three photos in ten get a wrong top-1 class. That is why the app shows alternatives and asks the "
                 "user to confirm: Explainable AI turns a known error rate into a correction step instead of a hidden failure.",
             ]),
             ("Runtime parity", [
                 "Model Evaluation also checked the ONNX Runtime export against the original checkpoint on six hundred and one "
                 "images: top-1 and top-3 agreement was complete. Parity shows the runtime reproduces the model; it is not an "
                 "accuracy measurement.",
             ]),
         ]),
    dict(file="11-notes-hybrid-search.md", kind="md", date="2026-08-25", author=OWNER,
         title="Notes: Hybrid Search with Reciprocal Rank Fusion",
         description="How CEREBRO combines keyword and semantic retrieval, and how to tell whether it works.",
         topics=["Semantic Search", "Retrieval-Augmented Generation", "Model Evaluation"], projects=["CEREBRO"],
         technologies=["PostgreSQL"], organizations=[], people=[], tags=["search", "notes"],
         body=[
             ("Why hybrid", [
                 "Written on 25 August 2026. Keyword search finds the exact acronym a person remembers; Semantic Search finds "
                 "the passage that says the same thing in other words. Neither is enough alone.",
             ]),
             ("Reciprocal rank fusion", [
                 "CEREBRO runs PostgreSQL full-text search and exact cosine similarity over stored vectors, then fuses the two "
                 "rankings by reciprocal rank. A passage near the top of either list rises; one that both lists like rises most.",
                 "The fused passages are what Retrieval-Augmented Generation hands to the model, so retrieval quality caps "
                 "answer quality.",
             ]),
             ("Checking it", [
                 "Model Evaluation for search uses a small labelled set: for each question, which fragments should come back. "
                 "Recall at five and the rank of the first correct fragment are the two numbers worth watching.",
             ]),
         ]),
    dict(file="12-cerebro-ground-truth-benchmark.pdf", kind="pdf", date="2026-09-05", author=OWNER,
         title="CEREBRO Ground Truth Benchmark (CEREBRO-GT v0.1)",
         description="A frozen, annotated benchmark for measuring the knowledge pipeline before it is tuned.",
         topics=["Provenance", "Model Evaluation", "Human-in-the-Loop Review"], projects=["CEREBRO"], technologies=[],
         organizations=[], people=[], tags=["benchmark"],
         body=[
             ("Why a benchmark", [
                 "The benchmark was frozen on 5 September 2026, before any tuning. Model Evaluation without a fixed reference "
                 "only measures how the pipeline changed, not whether it is right.",
             ]),
             ("Annotation schema", [
                 "Each item records the source artefact and its checksum, the expected fragments with their character ranges, "
                 "and the expected concepts. Annotation itself is Human-in-the-Loop Review: a person approves every label.",
             ]),
             ("Acceptance tests", [
                 "A pipeline run passes when every expected fragment is produced with the right Provenance and no fragment lacks "
                 "a source location. Concept extraction is scored separately, because wording can differ while meaning holds.",
             ]),
         ]),
    dict(file="13-group-7-minutes-2026-09-12.docx", kind="docx", date="2026-09-12", author=OWNER,
         title="Group 7 Meeting Minutes: 12 September 2026",
         description="Decisions on the benchmark, mandatory review, and reusing the pipeline telemetry pattern.",
         topics=["Human-in-the-Loop Review", "Provenance", "Model Evaluation", "Explainable AI"], projects=["CEREBRO", "MealSenseAI"],
         technologies=[], organizations=["NUS-ISS"], people=[], tags=["minutes"],
         body=[
             ("Attendees", ["Joselito Dizon (minutes) and Group 7 members of the NUS-ISS practice module. Meeting held on 12 September 2026."]),
             ("Decisions", [
                 "Freeze the ground truth benchmark as version 0.1 before tuning the pipeline, so Model Evaluation compares "
                 "against something that does not move.",
                 "Human-in-the-Loop Review stays mandatory: no artefact is registered on enrichment output alone.",
                 "Show pipeline stages and timings in both CEREBRO and MealSenseAI. Explainable AI and Provenance are the same "
                 "promise seen from two sides: show the work, and show where it came from.",
             ]),
             ("Actions", [
                 "Write up the proof-of-concept results by 24 September 2026.",
                 "Prepare the mid-term presentation for October 2026.",
             ]),
         ]),
    dict(file="14-knowledge-pipeline-poc-results.docx", kind="docx", date="2026-09-24", author=OWNER,
         title="Knowledge Pipeline Proof of Concept: Results",
         description="Steps one to six of the knowledge pipeline proof of concept, measured against the benchmark.",
         topics=["Knowledge Graphs", "Provenance", "Human-in-the-Loop Review", "Semantic Search"], projects=["CEREBRO"],
         technologies=["Ollama"], organizations=[], people=[], tags=["results"],
         body=[
             ("Scope", [
                 "Reported on 24 September 2026. The proof of concept implements the CEREBRO pipeline in notebooks before it "
                 "moves into the product, and is measured against the ground truth benchmark.",
             ]),
             ("What was built", [
                 "Files are inspected and their own metadata read first. A local model served by Ollama suggests titles, topics "
                 "and tags, and Human-in-the-Loop Review approves or corrects them before registration.",
                 "Text is segmented into fragments, each with its Provenance. Embeddings connect related fragments across "
                 "documents for Semantic Search, and shared topics form the first Knowledge Graphs of the library.",
             ]),
             ("Findings", [
                 "Deterministic segmentation reproduced every expected fragment and its location.",
                 "Model suggestions helped with topics but invented authors twice, which is why an author may only come from the "
                 "document's metadata or a printed byline.",
             ]),
         ]),
    dict(file="15-local-llm-evaluation-plan.pdf", kind="pdf", date="2026-09-28", author=OWNER,
         title="Local LLM Evaluation Plan",
         description="How small local models will be compared for grounded answering in both projects.",
         topics=["Local Language Models", "Retrieval-Augmented Generation", "Model Evaluation"], projects=["CEREBRO", "MealSenseAI"],
         technologies=["Ollama", "qwen3", "mxbai-embed-large"], organizations=[], people=[], tags=["plan"],
         body=[
             ("Goal", [
                 "Planned on 28 September 2026. Choose Local Language Models for answer phrasing in the MealSenseAI Meal Advisor "
                 "and for Retrieval-Augmented Generation in CEREBRO Recall. Every candidate runs through Ollama; no cloud API is used.",
             ]),
             ("Candidates", [
                 "qwen3 for answering, because it follows citation instructions well once its deliberation is stripped; "
                 "mxbai-embed-large for embeddings, because its vectors separate topics cleanly in a small library.",
             ]),
             ("Method", [
                 "Model Evaluation uses a labelled question set. A validator counts unsupported numbers and named things in each "
                 "answer; latency, tokens per second and GPU memory are measured on the home server, not estimated.",
             ]),
         ]),
    dict(file="16-meal-advisor-grounded-answers.pptx", kind="pptx", date="2026-10-02", author=OWNER,
         title="MealSenseAI Meal Advisor: Grounded Answers",
         description="Presentation on how the Meal Advisor answers from evidence and refuses to invent.",
         topics=["Retrieval-Augmented Generation", "Local Language Models", "Nutrition Estimation", "Explainable AI"],
         projects=["MealSenseAI"], technologies=["Ollama"], organizations=[], people=[], tags=["presentation"],
         body=[
             ("MealSenseAI Meal Advisor: Grounded Answers", ["Presented by Joselito Dizon", "2 October 2026"]),
             ("Evidence first", [
                 "The advisor drafts every answer from evidence: your meals, the food table, approved guidance",
                 "This is Retrieval-Augmented Generation over structured data rather than documents",
                 "Nutrition Estimation numbers come from the meal, never from the model"]),
             ("Where the model fits", [
                 "Local Language Models via Ollama may rephrase the draft",
                 "A validator rejects any new number or food",
                 "If validation fails, the draft is shown instead"]),
             ("Explaining itself", [
                 "Explainable AI: every reply lists its sources",
                 "Questions it cannot answer get an honest 'I don't know'"]),
         ]),
    dict(file="17-home-server-runbook-buddy.docx", kind="docx", date="2026-10-05", author=OWNER,
         title="Home Server Runbook: Buddy",
         description="How the home server hosts MealSenseAI and CEREBRO with containers, a GPU, Ollama and a tunnel.",
         topics=["Containerised Deployment", "Local Language Models"], projects=["CEREBRO", "MealSenseAI"],
         technologies=["Docker Compose", "Ollama", "Cloudflare Tunnel", "PostgreSQL"], organizations=[], people=[],
         tags=["runbook", "operations"],
         body=[
             ("Host", [
                 "Last reviewed on 5 October 2026. Buddy is an Ubuntu server with an NVIDIA GPU, running Docker Compose and "
                 "Ollama. Public access goes through a Cloudflare Tunnel, so no router ports are opened.",
             ]),
             ("Services", [
                 "Containerised Deployment keeps the projects apart: MealSenseAI and CEREBRO run as separate Compose projects, "
                 "each with its own PostgreSQL and its own host port.",
                 "Both projects share the Ollama daemon, so Local Language Models are pulled once and served to both.",
             ]),
             ("Rules", [
                 "Never run destructive volume-removal commands. Back up each database before a deployment, deploy only after "
                 "approval, and keep a rollback commit for every release.",
             ]),
         ]),
    dict(file="18-decision-log-embeddings-in-postgresql.md", kind="md", date="2026-10-10", author=OWNER,
         title="Decision Log: Embeddings Stay in PostgreSQL",
         description="Why CEREBRO keeps vectors in PostgreSQL instead of adding a vector database, and when to revisit.",
         topics=["Semantic Search", "Containerised Deployment"], projects=["CEREBRO"], technologies=["PostgreSQL", "Kubernetes"],
         organizations=[], people=[], tags=["decision"],
         body=[
             ("Decision", [
                 "Decided on 10 October 2026: embeddings for CEREBRO Semantic Search stay in PostgreSQL, searched by exact cosine "
                 "similarity. No separate vector database is added.",
             ]),
             ("Reasons", [
                 "A personal library holds thousands of fragments, not billions; exact search is fast enough and never misses.",
                 "One datastore keeps Containerised Deployment simple: one fewer service in Kubernetes and in Compose, one "
                 "fewer thing to back up.",
             ]),
             ("Revisit when", [
                 "A single user's library passes a few hundred thousand fragments, or query latency exceeds a second.",
                 "Switching embedding model orphans existing vectors, so any change must re-register the library.",
             ]),
         ]),
    dict(file="19-group-7-minutes-2026-10-14.docx", kind="docx", date="2026-10-14", author=OWNER,
         title="Group 7 Meeting Minutes: 14 October 2026",
         description="Choosing the local models, the demo environment, and review of the Recall answers.",
         topics=["Retrieval-Augmented Generation", "Local Language Models", "Containerised Deployment", "Human-in-the-Loop Review"],
         projects=["CEREBRO"], technologies=["Ollama", "qwen3", "mxbai-embed-large", "Docker Compose"], organizations=["NUS-ISS"],
         people=[], tags=["minutes"],
         body=[
             ("Attendees", ["Joselito Dizon (minutes) and Group 7 members of the NUS-ISS practice module. Meeting held on 14 October 2026."]),
             ("Decisions", [
                 "Adopt qwen3 and mxbai-embed-large, served by Ollama, as the Local Language Models for CEREBRO Recall, following the evaluation plan.",
                 "Retrieval-Augmented Generation answers must cite at least one passage, or abstain.",
                 "The demo runs by Containerised Deployment with Docker Compose, so markers need one command.",
                 "Human-in-the-Loop Review stays visible in the demo: show a document awaiting approval that Recall cannot see.",
             ]),
             ("Actions", ["Seed the demo library with related documents before the mid-term presentation on 20 October 2026."]),
         ]),
    dict(file="20-design-memo-glucose-mmol.docx", kind="docx", date="2026-10-24", author=OWNER,
         title="Design Memo: Glucose Estimates in mmol/L",
         description="Replacing the relative glucose index with mmol/L: pre-meal reading plus an estimated rise.",
         topics=["Glycaemic Response", "Nutrition Estimation", "Explainable AI"], projects=["MealSenseAI"], technologies=[],
         organizations=["American Diabetes Association"], people=[], tags=["design"],
         body=[
             ("Decision", [
                 "Agreed on 24 October 2026: the MealSenseAI forecast chart shows Glycaemic Response in mmol/L, as the user's pre-meal "
                 "reading plus the estimated rise from the meal.",
             ]),
             ("How the rise is estimated", [
                 "Nutrition Estimation supplies the carbohydrate and glycaemic load. Without readings, the rise is anchored to "
                 "typical glucose tolerance responses with a wide band, consistent with the American Diabetes Association's description of tolerance testing; after three meals with readings before and after "
                 "eating, it is calibrated to the user.",
             ]),
             ("Explaining it", [
                 "Explainable AI here means the label never hides: the curve is always called an estimate, even when it starts "
                 "from a measured reading, and it must never be used to adjust insulin or medication.",
             ]),
         ]),
    dict(file="21-cerebro-midterm-presentation.pptx", kind="pptx", date="2026-10-20", author=OWNER,
         title="CEREBRO Mid-term Presentation",
         description="Mid-term progress: what CEREBRO does today, how it is evaluated, and what comes next.",
         topics=["Knowledge Graphs", "Retrieval-Augmented Generation", "Provenance", "Human-in-the-Loop Review"],
         projects=["CEREBRO"], technologies=["PostgreSQL", "Ollama", "Next.js"], organizations=["NUS-ISS"], people=[],
         tags=["presentation"],
         body=[
             ("CEREBRO Mid-term Presentation", ["Presented by Joselito Dizon", "Group 7, NUS-ISS, 20 October 2026"]),
             ("Learn", [
                 "PDF, Word, PowerPoint and Markdown, extracted deterministically",
                 "Next.js web tier, FastAPI, and PostgreSQL for fragments and vectors",
                 "Human-in-the-Loop Review: nothing enters retrieval without approval"]),
             ("Connect", [
                 "The Galaxy draws Knowledge Graphs of confirmed topics and entities",
                 "Edges are co-occurrence, labelled as such, never inferred meaning"]),
             ("Recall", [
                 "Retrieval-Augmented Generation over approved fragments, phrased by a local model in Ollama",
                 "Every answer carries its Provenance down to the page or slide"]),
             ("Next", ["Seeded demo library, evaluation write-up, final demo by 30 November 2026"]),
         ]),
    dict(file="22-galaxy-design-notes.pdf", kind="pdf", date="2026-10-22", author=OWNER,
         title="Galaxy Design Notes: Co-occurrence, Not Claims",
         description="Why the Galaxy shows what documents share rather than what a model believes they mean.",
         topics=["Knowledge Graphs", "Explainable AI", "Provenance"], projects=["CEREBRO"], technologies=[], organizations=[],
         people=[], tags=["design"],
         body=[
             ("Principle", [
                 "Written on 22 October 2026. The Galaxy is CEREBRO's view of Knowledge Graphs, but its edges only say what the "
                 "data supports: two confirmed topics appear in the same registered document.",
             ]),
             ("Why not infer relationships", [
                 "A label like 'depends on' would be a claim no evidence here supports. Explainable AI means every edge can "
                 "answer 'why is this drawn?' with the documents behind it.",
                 "Each edge therefore carries its Provenance: the documents it rests on, and how many.",
             ]),
             ("Making it readable", [
                 "Clusters open first and fragments arrive on demand. An edge backed by a single document is kept but drawn only "
                 "when one of its ends is selected, so the opening view shows links that recur.",
                 "A library seeded with related documents shows this best: a shared vocabulary of topics produces recurring "
                 "edges instead of isolated islands.",
             ]),
         ]),
]

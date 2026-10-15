workspace "CEREBRO" "Adaptive Knowledge and Reasoning Digital Twin" {

    /*
     * C4 model for CEREBRO.
     *
     * Every element carries a status tag so one model shows both what exists
     * and what is planned:
     *
     *   Built    implemented, tested and committed
     *   Partial  present but incomplete or unverified
     *   Planned  not started; named here so the shape of the system is visible
     *
     * Open with Structurizr Lite:
     *   docker run -it --rm -p 8080:8080 \
     *     -v "$PWD/architecture/structurizr:/usr/local/structurizr" \
     *     structurizr/lite
     */

    model {
        owner = person "Owner" "A person building a private knowledge twin." "Person"

        cerebro = softwareSystem "CEREBRO" "Turns personal knowledge and experiences into a connected digital twin." {

            web = container "cerebro-web" "Landing, auth, The Construct, profile and settings. Proxies /api to the API so the browser sees one origin." "Next.js 16, React 19, TypeScript" "Built,Web"
            api = container "cerebro-api" "Authentication, profile and preferences; in time, the knowledge APIs." "FastAPI, Python 3.11" "Built,Api" {
                authRouter = component "Auth Router" "POST /signup, /login, /logout and GET /me." "FastAPI APIRouter" "Built"
                deps = component "Dependencies" "Resolves the session cookie or bearer token to a User, or 401." "FastAPI Depends" "Built"
                userService = component "User Service" "Account creation and credential checking, free of HTTP concerns." "Python" "Built"
                security = component "Security" "Argon2id hashing and JWT issue/verify." "argon2-cffi, PyJWT" "Built"
                userModel = component "User Model" "users table: UUID id, unique lowercased email, Argon2id hash." "SQLAlchemy 2" "Built"
                health = component "Health" "GET /api/health, including database reachability." "FastAPI" "Built"

                profileRouter = component "Profile Router" "GET/PATCH /profile and /preferences, GET /account, POST /account/password." "FastAPI APIRouter" "Built"
                profileService = component "Profile Service" "Profile and preferences persistence; deterministic completion; cloud-AI consent gating." "Python" "Built"
                profileModel = component "Profile & Preferences Models" "user_profiles and user_preferences, each keyed by the user id." "SQLAlchemy 2" "Built"

                artifactRouter = component "Artifact Router" "Upload, list and fetch artifacts." "FastAPI" "Planned"
                searchRouter = component "Search / Recall Router" "Semantic search and recall over the twin." "FastAPI" "Planned"
            }
            db = container "PostgreSQL" "Users, profiles and preferences today; artifacts and metadata next." "PostgreSQL 16" "Built,Db"

            worker = container "cerebro-worker" "Asynchronous ingestion and enrichment pipeline." "Python" "Planned"
            objectStore = container "Object Store" "Original uploaded artifacts." "MinIO" "Planned,Db"
            vectorDb = container "Vector Store" "Embeddings for semantic search and RAG." "Qdrant" "Planned,Db"
            graphDb = container "Knowledge Graph" "Entities and the relationships between them." "Neo4j" "Planned,Db"
            bus = container "Event Bus" "Decouples ingestion from enrichment." "Kafka" "Planned"
            llm = container "Local LLM" "Reasoning and answer generation, kept on-device." "Ollama" "Planned"

            # --- what exists today -------------------------------------------
            owner -> web "Signs up, signs in, uses The Construct" "HTTPS" "Built"
            web -> api "Proxies /api; validates the session on every protected render" "HTTP/JSON" "Built"
            api -> db "Reads and writes users" "SQL over psycopg" "Built"

            # --- what comes next ---------------------------------------------
            web -> api "Uploads artifacts, searches, recalls" "HTTP/JSON" "Planned"
            api -> objectStore "Stores and serves original artifacts" "S3 API" "Planned"
            api -> bus "Publishes artifact.ingested" "Kafka" "Planned"
            bus -> worker "Delivers ingestion events" "Kafka" "Planned"
            worker -> objectStore "Reads originals" "S3 API" "Planned"
            worker -> llm "Extracts entities, summarises" "HTTP" "Planned"
            worker -> vectorDb "Writes embeddings" "gRPC" "Planned"
            worker -> graphDb "Writes entities and relationships" "Bolt" "Planned"
            worker -> db "Updates artifact status" "SQL" "Planned"
            api -> vectorDb "Semantic search" "gRPC" "Planned"
            api -> graphDb "Traverses connections" "Bolt" "Planned"
            api -> llm "Grounded answers over retrieved context" "HTTP" "Planned"
        }

        # --- how the API components fit together ------------------------------
        web -> authRouter "Signup, login, logout, session check" "HTTP/JSON" "Built"
        web -> profileRouter "Reads and writes profile, preferences and account" "HTTP/JSON" "Built"
        authRouter -> deps "Guards /me with"
        profileRouter -> deps "Resolves the user from the session with"
        profileRouter -> profileService "Delegates to"
        profileService -> profileModel "Persists through"
        profileModel -> db "Reads and writes"
        authRouter -> userService "Delegates to"
        deps -> security "Verifies tokens with"
        deps -> userService "Loads the user with"
        userService -> security "Hashes and verifies passwords with"
        userService -> userModel "Persists through"
        userModel -> db "Reads and writes"

        # --- deployment: local Kubernetes ------------------------------------
        deploymentEnvironment "Local Kubernetes" {
            deploymentNode "Developer machine" "" "Docker Desktop, kind or minikube" {
                deploymentNode "Kubernetes cluster" "" "Kubernetes 1.31" {
                    deploymentNode "namespace: cerebro" "" "Namespace" {
                        deploymentNode "Deployment/cerebro-web" "" "1 replica" {
                            containerInstance web
                        }
                        deploymentNode "Deployment/cerebro-api" "" "1 replica, init container runs alembic upgrade head" {
                            containerInstance api
                        }
                        deploymentNode "StatefulSet/cerebro-postgres" "" "1 replica, 5Gi PersistentVolumeClaim" {
                            containerInstance db
                        }
                    }
                }
            }
        }
    }

    views {
        systemContext cerebro "SystemContext" "Who uses CEREBRO and what it is." {
            include *
            autolayout lr
        }

        container cerebro "Containers" "Containers today (solid) and planned (dashed)." {
            include *
            autolayout lr
        }

        component api "ApiComponents" "Inside cerebro-api." {
            include *
            autolayout lr
        }

        deployment cerebro "Local Kubernetes" "Deployment" "How it runs on a local cluster." {
            include *
            autolayout lr
        }

        styles {
            element "Person" {
                shape person
                background #2a5d9f
                color #ffffff
            }
            element "Software System" {
                background #14171c
                color #ffffff
            }
            element "Container" {
                background #ffffff
                color #14171c
                stroke #cfd5de
            }
            element "Built" {
                background #2a5d9f
                color #ffffff
                stroke #234f88
            }
            element "Partial" {
                background #eef3fa
                color #14171c
                stroke #2a5d9f
            }
            element "Planned" {
                background #f7f8fa
                color #636c7a
                stroke #cfd5de
                opacity 60
            }
            element "Db" {
                shape cylinder
            }
            element "Web" {
                shape webBrowser
            }
            relationship "Planned" {
                style dashed
                color #636c7a
                opacity 60
            }
            relationship "Built" {
                color #14171c
                thickness 2
            }
        }
    }
}

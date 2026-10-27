# Codebase reference

Scope update: reference-model, local-training and scoring descriptions below remain
valid for Sia's nonprivate ensemble. Statements describing plaintext federation
or absence of DP refer to that reference/research path. Current browser
collaboration uses the private four-round adaptive ensemble described in
[PRIVACY_AUDIT.md](PRIVACY_AUDIT.md) and [the new evidence](../artifacts/dp_level3_ensemble/).


This map describes the active application and its reusable model modules. For behavior and data flow, read the [implementation guide](IMPLEMENTATION_GUIDE.md). The symbol index links directly to implementation lines; historical research modules are identified separately.

## Directory map

| Directory | Responsibility |
|---|---|
| `streaming/app/` | Current dashboard backend, workers, state and transfers |
| `streaming/web/index.html` | Current browser UI: layout, tab navigation, form validation, polling, replay, graph and explanation rendering |
| `src/gnn/` | Temporal model and continual/federated algorithms |
| `distributed_federation/` | Kafka worker/coordinator protocol, schema, serialization and checkpoints |
| `xai/src/` | Explanation algorithms, catalogs and older report tooling; grouped and ensemble explainers are reused by the current dashboard |
| `scripts/` | Data preparation, audits, experiment launchers and dashboard acceptance |
| `configs/` | Frozen original and adaptive research experiment settings |
| `data/final_temporal_dataset/` | Prepared split/bank graphs, feature allowlists and quality reports |
| `artifacts/` | Saved checkpoints, manifests, research metrics and experiment evidence |
| `tests/`, `xai/tests/` | Regression suites; real transport tests are separate scripts |
| `docs/` | Current implementation/review guides and preserved research reports |
| `streaming/.local/` | Ignored runtime jobs, logs, active selections, SQLite state and downloaded files |
| `ibm_aml/`, `src/gnn/legacy/`, `scripts/historical/` | Earlier duplicated/superseded code and research context; not the dashboard entry point |

## Main call chains

- **Launch:** `dashboard.main → server → Handler` creates the local services and serves `index.html`.
- **Select:** `Overview.load → reference_model → validate_selected` resolves the original ensemble or a verified completed local/shared version.
- **Train:** `LocalTraining.start → worker → check_dataset → train_ensemble → train_client` performs data checks and June/July replay, then saves selected members.
- **Score:** `Monitoring.start → worker → load_runtime → score_models → score_stream` reconstructs causal memory and persists validation scores.
- **Explain:** `Explanations.start → worker → explain → explain_groups` reconstructs the replay model and computes grouped feature contributions.
- **Collaborate:** `Collaboration.start → RunController.start → runner → bank_worker.run / aggregator.run` exchanges and trains model states; `aggregate_adaptive` harmonizes each seed.
- **Transfer:** `Transfers.start → signed chunks → receiver verification → signed receipt` preserves arbitrary file bytes and delivery evidence.
- **Report:** `research_results`, monitoring/training jobs and collaboration/transfer stores supply the Results page. `privacy_status` supplies the Privacy page.

## Frontend function map

| Function | Responsibility |
|---|---|
| `showTab` | Switches panels and accessible selected navigation state |
| `post` | Sends JSON mutations with the session token |
| `loadOverview` / `renderOverview` | Loads bank identity, model provenance and correctly scoped evaluation |
| `refreshTraining` | Renders data checks, real progress, logs, cancellation and activation controls |
| `fedProfile` / `loadFedProfile` | Reads/writes the collaboration form |
| `fedAction` / `refreshCollaboration` | Starts/checks/controls the local participant and displays roster/round events |
| `refreshMonitoring` | Polls scorer status and lists completed bank-specific replays |
| `renderReplay` / `resetReplay` | Reveals/filter scores, controls replay state and enables relevant buttons |
| `inspectTransaction` | Draws account connections from events already revealed |
| `requestExplanation` / `refreshExplanations` | Requests and renders replay-specific group contributions and member scores |
| `refreshResults` / `metricText` | Displays saved and new evidence with the correct ensemble versus multi-run interpretation |
| `refresh` / transfer handlers | Renders transfer history, connection checks, downloads and recovery actions |

## Python modules and symbols

Class methods appear as `Class.method`; nested worker callbacks are internal to their containing function. Signatures and source links identify exact implementations. Docstrings summarize behavior where available.

### `streaming/app/dashboard.py`

Loopback HTTP routing, session/Origin protection and service lifecycle.

| Symbol | Purpose / source |
|---|---|
| `server(root, port=8765)` | Server. [Source](../streaming/app/dashboard.py#L28) |
| `main()` | Main. [Source](../streaming/app/dashboard.py#L219) |

### `streaming/app/final_model.py`

Verified three-member model selection, fixed encoders, runtime loading and probability averaging.

| Symbol | Purpose / source |
|---|---|
| `digest(path)` | Digest. [Source](../streaming/app/final_model.py#L15) |
| `reference_model(bank, repo=REPO)` | Reference model. [Source](../streaming/app/final_model.py#L19) |
| `validate_selected(selected)` | Validate selected. [Source](../streaming/app/final_model.py#L37) |
| `frozen_encoders(repo=REPO)` | Frozen encoders. [Source](../streaming/app/final_model.py#L50) |
| `build_ensemble(schema, checkpoints=True)` | Build ensemble. [Source](../streaming/app/final_model.py#L56) |
| `load_runtime(selected, dataset, bank)` | Load only training/validation. Shared encoders never fit on validation. [Source](../streaming/app/final_model.py#L69) |
| `score_models(models, static, streams, check=lambda: None, progress=lambda _: None)` | Score models. [Source](../streaming/app/final_model.py#L103) |
| `reference_evidence(repo=REPO)` | Reference evidence. [Source](../streaming/app/final_model.py#L118) |

### `streaming/app/ensemble_training.py`

Adapts all three members on June/July context replay; selects each using August validation.

| Symbol | Purpose / source |
|---|---|
| `train_ensemble(job, folder, update, check)` | Train ensemble. [Source](../streaming/app/ensemble_training.py#L13) |

### `streaming/app/local_training.py`

Data quality, file fingerprints, worker jobs, cancellation and explicit model activation.

| Symbol | Purpose / source |
|---|---|
| `now()` | Now. [Source](../streaming/app/local_training.py#L18) |
| `write_json(path, data)` | Write json. [Source](../streaming/app/local_training.py#L21) |
| `read_json(path, fallback=None)` | Read json. [Source](../streaming/app/local_training.py#L34) |
| `check_dataset(dataset, bank)` | Check dataset. [Source](../streaming/app/local_training.py#L40) |
| **`LocalTraining`** | Data quality, file fingerprints, worker jobs, cancellation and explicit model activation. [Source](../streaming/app/local_training.py#L97) |
| `LocalTraining.__init__(self, root)` | Init. [Source](../streaming/app/local_training.py#L98) |
| `LocalTraining.jobs(self)` | Jobs. [Source](../streaming/app/local_training.py#L103) |
| `LocalTraining.status(self)` | Status. [Source](../streaming/app/local_training.py#L106) |
| `LocalTraining.start(self, data, bank)` | Start. [Source](../streaming/app/local_training.py#L127) |
| `LocalTraining.cancel(self, key)` | Cancel. [Source](../streaming/app/local_training.py#L171) |
| `LocalTraining.activate(self, key, bank)` | Activate. [Source](../streaming/app/local_training.py#L178) |
| `LocalTraining.close(self)` | Close. [Source](../streaming/app/local_training.py#L191) |
| `worker(path)` | Worker. [Source](../streaming/app/local_training.py#L203) |

### `streaming/app/monitoring.py`

Scores validation with the selected model and persists bank-scoped replay rows and metrics.

| Symbol | Purpose / source |
|---|---|
| **`Monitoring`** | Scores validation with the selected model and persists bank-scoped replay rows and metrics. [Source](../streaming/app/monitoring.py#L13) |
| `Monitoring.__init__(self, root)` | Init. [Source](../streaming/app/monitoring.py#L14) |
| `Monitoring.status(self, bank)` | Status. [Source](../streaming/app/monitoring.py#L24) |
| `Monitoring.start(self, data, bank)` | Start. [Source](../streaming/app/monitoring.py#L27) |
| `Monitoring.cancel(self, key, bank)` | Cancel. [Source](../streaming/app/monitoring.py#L42) |
| `Monitoring.rows(self, key, bank)` | Rows. [Source](../streaming/app/monitoring.py#L47) |
| `Monitoring.close(self)` | Close. [Source](../streaming/app/monitoring.py#L50) |
| `worker(path)` | Worker. [Source](../streaming/app/monitoring.py#L58) |

### `streaming/app/explanations.py`

Asynchronous replay-specific exact grouped SHAP and prediction consistency checks.

| Symbol | Purpose / source |
|---|---|
| **`Explanations`** | Asynchronous replay-specific exact grouped SHAP and prediction consistency checks. [Source](../streaming/app/explanations.py#L12) |
| `Explanations.__init__(self, root, monitoring)` | Init. [Source](../streaming/app/explanations.py#L13) |
| `Explanations.status(self, bank)` | Status. [Source](../streaming/app/explanations.py#L21) |
| `Explanations.start(self, data, bank)` | Start. [Source](../streaming/app/explanations.py#L24) |
| `Explanations.close(self)` | Close. [Source](../streaming/app/explanations.py#L40) |
| `explain(job)` | Explain. [Source](../streaming/app/explanations.py#L45) |
| `worker(path)` | Worker. [Source](../streaming/app/explanations.py#L96) |

### `streaming/app/privacy.py`

Reports actual DP, integrity, encryption, secure-aggregation and explanation boundaries.

| Symbol | Purpose / source |
|---|---|
| `privacy_status()` | Privacy status. [Source](../streaming/app/privacy.py#L3) |

### `streaming/app/overview.py`

Persists bank selection and reports model/evaluation provenance.

| Symbol | Purpose / source |
|---|---|
| **`Overview`** | Persists bank selection and reports model/evaluation provenance. [Source](../streaming/app/overview.py#L10) |
| `Overview.__init__(self, root, repo=REPO)` | Init. [Source](../streaming/app/overview.py#L11) |
| `Overview.save(self, data)` | Save. [Source](../streaming/app/overview.py#L15) |
| `Overview.load(self)` | Load. [Source](../streaming/app/overview.py#L30) |

### `streaming/app/results.py`

Reads saved baseline and final ensemble results without rescoring September.

| Symbol | Purpose / source |
|---|---|
| `research_results(repo=REPO)` | Research results. [Source](../streaming/app/results.py#L6) |

### `streaming/app/collaboration.py`

Validates collaboration profiles, prepares/checks topics, supervises workers and selects verified shared ensembles.

| Symbol | Purpose / source |
|---|---|
| **`Collaboration`** | Validates collaboration profiles, prepares/checks topics, supervises workers and selects verified shared ensembles. [Source](../streaming/app/collaboration.py#L20) |
| `Collaboration.__init__(self, root)` | Init. [Source](../streaming/app/collaboration.py#L21) |
| `Collaboration.defaults(self)` | Defaults. [Source](../streaming/app/collaboration.py#L28) |
| `Collaboration.profile(self)` | Profile. [Source](../streaming/app/collaboration.py#L31) |
| `Collaboration.validate(self, data)` | Validate. [Source](../streaming/app/collaboration.py#L33) |
| `Collaboration.save(self, data)` | Save. [Source](../streaming/app/collaboration.py#L57) |
| `Collaboration.config(self, profile)` | Config. [Source](../streaming/app/collaboration.py#L61) |
| `Collaboration.preflight(self, data, bank, prepare=False)` | Preflight. [Source](../streaming/app/collaboration.py#L71) |
| `Collaboration.start(self, data, bank)` | Start. [Source](../streaming/app/collaboration.py#L102) |
| `Collaboration.control(self, run, cancel=False)` | Control. [Source](../streaming/app/collaboration.py#L137) |
| `Collaboration.select_model(self, run_id, round_id, bank)` | Select model. [Source](../streaming/app/collaboration.py#L140) |
| `Collaboration.status(self, bank)` | Status. [Source](../streaming/app/collaboration.py#L162) |

### `streaming/app/controller.py`

Starts allowlisted worker roles from configuration snapshots and exposes stop/cancel/status.

| Symbol | Purpose / source |
|---|---|
| **`RunController`** | Starts only known federation roles; credentials stay in the child environment. [Source](../streaming/app/controller.py#L19) |
| `RunController.__init__(self, state_dir=DEFAULT_STATE, python=sys.executable)` | Init. [Source](../streaming/app/controller.py#L22) |
| `RunController.start(self, config_path, role, client_id=None, environment=None, output=None)` | Start. [Source](../streaming/app/controller.py#L27) |
| `RunController.stop(self, run, cancel=False)` | Stop. [Source](../streaming/app/controller.py#L52) |
| `RunController.status(self)` | Status. [Source](../streaming/app/controller.py#L56) |
| `main()` | Main. [Source](../streaming/app/controller.py#L65) |

### `streaming/app/runner.py`

Child-process lifecycle, runtime lock, events and durable completion/failure status.

| Symbol | Purpose / source |
|---|---|
| `execute(config_path, role, state_dir, client_id=None)` | Execute. [Source](../streaming/app/runner.py#L13) |
| `main()` | Main. [Source](../streaming/app/runner.py#L49) |

### `streaming/app/state.py`

SQLite records for supervised runs, events and control requests.

| Symbol | Purpose / source |
|---|---|
| `now()` | Now. [Source](../streaming/app/state.py#L10) |
| **`StateStore`** | One short transaction per write; usable by a future API while training runs. [Source](../streaming/app/state.py#L14) |
| `StateStore.__init__(self, path)` | Init. [Source](../streaming/app/state.py#L17) |
| `StateStore.connect(self)` | Connect. [Source](../streaming/app/state.py#L35) |
| `StateStore.begin(self, run_id, actor, config)` | Begin. [Source](../streaming/app/state.py#L45) |
| `StateStore.interrupt_previous(self)` | Interrupt previous. [Source](../streaming/app/state.py#L52) |
| `StateStore.emit(self, run, kind, round_id=None, **details)` | Emit. [Source](../streaming/app/state.py#L57) |
| `StateStore.finish(self, run, status)` | Finish. [Source](../streaming/app/state.py#L63) |
| `StateStore.request_control(self, run, action)` | Request control. [Source](../streaming/app/state.py#L69) |
| `StateStore.control(self, run)` | Control. [Source](../streaming/app/state.py#L86) |
| `StateStore.runs(self)` | Runs. [Source](../streaming/app/state.py#L91) |
| `StateStore.events(self, run, after=0, limit=500)` | Events. [Source](../streaming/app/state.py#L95) |

### `streaming/app/locking.py`

Cross-process exclusive ownership of a state directory.

| Symbol | Purpose / source |
|---|---|
| **`RuntimeLock`** | Cross-process exclusive ownership of a state directory. [Source](../streaming/app/locking.py#L6) |
| `RuntimeLock.__init__(self, path)` | Init. [Source](../streaming/app/locking.py#L7) |
| `RuntimeLock.__enter__(self)` | Enter. [Source](../streaming/app/locking.py#L11) |
| `RuntimeLock.__exit__(self, *args)` | Exit. [Source](../streaming/app/locking.py#L31) |

### `streaming/app/settings.py`

Validates and persists non-secret manual-transfer preferences.

| Symbol | Purpose / source |
|---|---|
| `validate_settings(data)` | Validate settings. [Source](../streaming/app/settings.py#L12) |
| **`Settings`** | Validates and persists non-secret manual-transfer preferences. [Source](../streaming/app/settings.py#L32) |
| `Settings.__init__(self, root)` | Init. [Source](../streaming/app/settings.py#L33) |
| `Settings.load(self)` | Load. [Source](../streaming/app/settings.py#L37) |
| `Settings.save(self, data)` | Save. [Source](../streaming/app/settings.py#L48) |

### `streaming/app/transfers.py`

Opaque file uploads, signed chunk transfer, verification, receipts, cancellation, retries and recovery.

| Symbol | Purpose / source |
|---|---|
| `safe_filename(value)` | Download label only. Storage always uses application-generated IDs. [Source](../streaming/app/transfers.py#L21) |
| **`Transfers`** | Opaque file uploads, signed chunk transfer, verification, receipts, cancellation, retries and recovery. [Source](../streaming/app/transfers.py#L33) |
| `Transfers.__init__(self, root)` | Init. [Source](../streaming/app/transfers.py#L34) |
| `Transfers.connect(self)` | Connect. [Source](../streaming/app/transfers.py#L63) |
| `Transfers.history(self)` | History. [Source](../streaming/app/transfers.py#L71) |
| `Transfers.update(self, job, **values)` | Update. [Source](../streaming/app/transfers.py#L75) |
| `Transfers.upload(self, payload)` | Upload. [Source](../streaming/app/transfers.py#L81) |
| `Transfers.write_file(self, name, payload)` | Write file. [Source](../streaming/app/transfers.py#L88) |
| `Transfers.start(self, settings)` | Start. [Source](../streaming/app/transfers.py#L100) |
| `Transfers.get_job(self, key)` | Get job. [Source](../streaming/app/transfers.py#L151) |
| `Transfers.retry(self, key, transfer_id)` | Retry. [Source](../streaming/app/transfers.py#L158) |
| `Transfers.recover(self, key)` | Recover. [Source](../streaming/app/transfers.py#L173) |
| `Transfers.recover_receipt(self, job, secret)` | Recover receipt. [Source](../streaming/app/transfers.py#L205) |
| `Transfers.close(self)` | Close. [Source](../streaming/app/transfers.py#L219) |
| `Transfers.cancel(self, key)` | Cancel. [Source](../streaming/app/transfers.py#L226) |
| `Transfers.run(self, job, broker, secret, payload)` | Run. [Source](../streaming/app/transfers.py#L232) |
| `Transfers.check_cancel(self)` | Check cancel. [Source](../streaming/app/transfers.py#L260) |
| `Transfers.check_connection(self, broker)` | Check connection. [Source](../streaming/app/transfers.py#L264) |
| `Transfers.send(self, job, broker, secret, payload)` | Send. [Source](../streaming/app/transfers.py#L280) |
| `Transfers.wait_receipt(self, job, broker, secret, token)` | Wait receipt. [Source](../streaming/app/transfers.py#L325) |
| `Transfers.publish_receipt(self, job, broker, secret, token)` | Publish receipt. [Source](../streaming/app/transfers.py#L365) |
| `Transfers.receive(self, job, broker, secret)` | Receive. [Source](../streaming/app/transfers.py#L379) |

### `streaming/app/peer_checks.py`

Signed peer challenge/response and local readiness evidence.

| Symbol | Purpose / source |
|---|---|
| **`PeerChecks`** | Signed peer challenge/response and local readiness evidence. [Source](../streaming/app/peer_checks.py#L13) |
| `PeerChecks.__init__(self)` | Init. [Source](../streaming/app/peer_checks.py#L14) |
| `PeerChecks.close(self)` | Close. [Source](../streaming/app/peer_checks.py#L22) |
| `PeerChecks.configure(self, broker, secret, local_id)` | Configure. [Source](../streaming/app/peer_checks.py#L27) |
| `PeerChecks.envelope(kind, source, target, nonce, secret)` | Envelope. [Source](../streaming/app/peer_checks.py#L41) |
| `PeerChecks.handle(self, raw, secret, local_id)` | Return a signed response or signal a matching pending challenge. [Source](../streaming/app/peer_checks.py#L46) |
| `PeerChecks.listen(self, broker, secret, local_id)` | Listen. [Source](../streaming/app/peer_checks.py#L72) |
| `PeerChecks.check(self, broker, secret, local_id, peer_id)` | Check. [Source](../streaming/app/peer_checks.py#L98) |

### `streaming/app/launcher.py`

Prerequisite checks, transfer-secret prompt and optional browser launch.

| Symbol | Purpose / source |
|---|---|
| `prerequisites(state_dir)` | Prerequisites. [Source](../streaming/app/launcher.py#L20) |
| `main(argv=None)` | Main. [Source](../streaming/app/launcher.py#L35) |

### `distributed_federation/common/model_runtime.py`

Frozen encoders, three-model runtime, replay training, safetensors serialization and seed-wise temporal harmonization.

| Symbol | Purpose / source |
|---|---|
| **`RuntimeData`** | Frozen encoders, three-model runtime, replay training, safetensors serialization and seed-wise temporal harmonization. [Source](../distributed_federation/common/model_runtime.py#L21) |
| `_imports()` | Imports. [Source](../distributed_federation/common/model_runtime.py#L29) |
| `prepare_runtime(config: FederationConfig, bank: str)` | Prepare runtime. [Source](../distributed_federation/common/model_runtime.py#L41) |
| `serialize_state(state: dict[str, Any])` | Serialize state. [Source](../distributed_federation/common/model_runtime.py#L72) |
| `deserialize_state(payload: bytes)` | Deserialize state. [Source](../distributed_federation/common/model_runtime.py#L79) |
| `validate_state(candidate: dict[str, Any], reference: dict[str, Any])` | Validate state. [Source](../distributed_federation/common/model_runtime.py#L85) |
| `load_initial_checkpoint(model: Any, path: Path \| None)` | Load initial checkpoint. [Source](../distributed_federation/common/model_runtime.py#L103) |
| `train_local(runtime: RuntimeData, config: FederationConfig, round_id: int, client_index: int)` | Train local. [Source](../distributed_federation/common/model_runtime.py#L130) |
| `fedavg(states: list[dict[str, Any]], weights: list[int])` | Fedavg. [Source](../distributed_federation/common/model_runtime.py#L168) |
| `save_state_and_manifest(state: dict[str, Any], output_dir: Path, round_id: int, manifest: dict[str, Any])` | Save state and manifest. [Source](../distributed_federation/common/model_runtime.py#L189) |
| **`FrozenEncoder`** | Apply the shared demo preprocessing contract without reading other banks. [Source](../distributed_federation/common/model_runtime.py#L199) |
| `FrozenEncoder.__init__(self, specification)` | Init. [Source](../distributed_federation/common/model_runtime.py#L201) |
| `FrozenEncoder.transform(self, frame)` | Transform. [Source](../distributed_federation/common/model_runtime.py#L203) |
| `prepare_frozen_runtime(config, bank=None)` | Prepare frozen runtime. [Source](../distributed_federation/common/model_runtime.py#L220) |
| `aggregate_adaptive(states, global_state)` | Equal-client temporal harmonization applied independently to each seed. [Source](../distributed_federation/common/model_runtime.py#L255) |

### `distributed_federation/common/config.py`

Typed federation configuration, path resolution, roster checks and protocol selection.

| Symbol | Purpose / source |
|---|---|
| **`ClientConfig`** | Typed federation configuration, path resolution, roster checks and protocol selection. [Source](../distributed_federation/common/config.py#L22) |
| **`FederationConfig`** | Typed federation configuration, path resolution, roster checks and protocol selection. [Source](../distributed_federation/common/config.py#L28) |
| `FederationConfig.client(self, client_id: str)` | Client. [Source](../distributed_federation/common/config.py#L54) |
| `_positive_int(raw: dict[str, Any], name: str)` | Positive int. [Source](../distributed_federation/common/config.py#L62) |
| `_repo_path(value: str \| None)` | Repo path. [Source](../distributed_federation/common/config.py#L69) |
| `load_config(path: str \| Path, broker_override: str \| None=None)` | Load config. [Source](../distributed_federation/common/config.py#L76) |
| `secret_env_name(client_id: str)` | Secret env name. [Source](../distributed_federation/common/config.py#L170) |

### `distributed_federation/common/protocol.py`

Signed chunk envelopes, hashes, run/round identity and reassembly.

| Symbol | Purpose / source |
|---|---|
| `canonical_json(value: Any)` | Canonical json. [Source](../distributed_federation/common/protocol.py#L21) |
| `sha256_bytes(payload: bytes)` | Sha256 bytes. [Source](../distributed_federation/common/protocol.py#L25) |
| `_signature(message: dict[str, Any], secret: str)` | Signature. [Source](../distributed_federation/common/protocol.py#L29) |
| `create_chunks(payload: bytes, metadata: dict[str, Any], secret: str, chunk_size: int)` | Create chunks. [Source](../distributed_federation/common/protocol.py#L34) |
| `peek_sender(raw: bytes)` | Peek sender. [Source](../distributed_federation/common/protocol.py#L61) |
| `verify_chunk(raw: bytes, secret: str)` | Verify chunk. [Source](../distributed_federation/common/protocol.py#L68) |
| **`_Pending`** | Signed chunk envelopes, hashes, run/round identity and reassembly. [Source](../distributed_federation/common/protocol.py#L94) |
| **`ChunkAssembler`** | Signed chunk envelopes, hashes, run/round identity and reassembly. [Source](../distributed_federation/common/protocol.py#L100) |
| `ChunkAssembler.__init__(self, max_payload_bytes: int=100000000, ttl_seconds: int=900)` | Init. [Source](../distributed_federation/common/protocol.py#L101) |
| `ChunkAssembler.add(self, message: dict[str, Any])` | Add. [Source](../distributed_federation/common/protocol.py#L106) |
| `ChunkAssembler._discard_expired(self)` | Discard expired. [Source](../distributed_federation/common/protocol.py#L143) |
| `verify_for_run(raw: bytes, secret: str, run_id: str)` | Ignore retained other-run traffic; every current-run message still requires HMAC. [Source](../distributed_federation/common/protocol.py#L149) |

### `distributed_federation/common/kafka_io.py`

Kafka clients and bounded payload publication.

| Symbol | Purpose / source |
|---|---|
| `make_producer(broker: str)` | Make producer. [Source](../distributed_federation/common/kafka_io.py#L11) |
| `make_consumer(broker: str, group_id: str, topics: Iterable[str])` | Make consumer. [Source](../distributed_federation/common/kafka_io.py#L24) |
| `publish_payload(producer: Any, topic: str, payload: bytes, metadata: dict[str, Any], secret: str, chunk_size: int)` | Publish payload. [Source](../distributed_federation/common/kafka_io.py#L38) |

### `distributed_federation/common/checkpoints.py`

Atomic checkpoint/manifest/commit-marker writes and verification.

| Symbol | Purpose / source |
|---|---|
| `atomic_write(path, payload)` | Atomic write. [Source](../distributed_federation/common/checkpoints.py#L9) |
| `save_checkpoint(payload, output_dir, round_id, manifest)` | Save checkpoint. [Source](../distributed_federation/common/checkpoints.py#L24) |
| `verify_checkpoint(output_dir, round_id)` | Verify checkpoint. [Source](../distributed_federation/common/checkpoints.py#L46) |

### `distributed_federation/common/control.py`

Cooperative stop/cancel checks inside workers.

| Symbol | Purpose / source |
|---|---|
| **`RunCancelled`** | Cooperative stop/cancel checks inside workers. [Source](../distributed_federation/common/control.py#L6) |
| **`RunStopped`** | Cooperative stop/cancel checks inside workers. [Source](../distributed_federation/common/control.py#L9) |
| `check_control(round_boundary=False)` | Check control. [Source](../distributed_federation/common/control.py#L12) |
| `control_source(source)` | Control source. [Source](../distributed_federation/common/control.py#L21) |

### `distributed_federation/common/events.py`

Structured event reporting from model and transport code.

| Symbol | Purpose / source |
|---|---|
| `emit(kind, round_id=None, **details)` | Emit. [Source](../distributed_federation/common/events.py#L8) |
| `event_sink(sink)` | Event sink. [Source](../distributed_federation/common/events.py#L15) |

### `distributed_federation/central/aggregator.py`

Coordinator readiness, model broadcast, client-update validation, aggregation and verified aggregate publication.

| Symbol | Purpose / source |
|---|---|
| `parse_args()` | Parse args. [Source](../distributed_federation/central/aggregator.py#L28) |
| `required_secret(name: str)` | Required secret. [Source](../distributed_federation/central/aggregator.py#L35) |
| `utc_now()` | Utc now. [Source](../distributed_federation/central/aggregator.py#L42) |
| `main()` | Main. [Source](../distributed_federation/central/aggregator.py#L46) |
| `run(config)` | Callable entry point; same learning loop as the original CLI. [Source](../distributed_federation/central/aggregator.py#L52) |

### `distributed_federation/client/bank_worker.py`

Bank readiness, model reception, local training, update publication and aggregate reception.

| Symbol | Purpose / source |
|---|---|
| `parse_args()` | Parse args. [Source](../distributed_federation/client/bank_worker.py#L24) |
| `required_secret(name: str)` | Required secret. [Source](../distributed_federation/client/bank_worker.py#L32) |
| `main()` | Main. [Source](../distributed_federation/client/bank_worker.py#L39) |
| `run(config, client_id)` | Callable entry point used by both the CLI and process supervisor. [Source](../distributed_federation/client/bank_worker.py#L45) |

### `src/gnn/causal_temporal_graphsage.py`

Chronological data loading, feature encoding, Temporal GraphSAGE/GRU memory, TBPTT, metrics and original local training.

| Symbol | Purpose / source |
|---|---|
| **`Events`** | Chronological data loading, feature encoding, Temporal GraphSAGE/GRU memory, TBPTT, metrics and original local training. [Source](../src/gnn/causal_temporal_graphsage.py#L54) |
| `Events.to(self, device: torch.device)` | To. [Source](../src/gnn/causal_temporal_graphsage.py#L61) |
| `Events.__len__(self)` | Len. [Source](../src/gnn/causal_temporal_graphsage.py#L64) |
| **`TemporalState`** | Chronological data loading, feature encoding, Temporal GraphSAGE/GRU memory, TBPTT, metrics and original local training. [Source](../src/gnn/causal_temporal_graphsage.py#L69) |
| `TemporalState.detached(self)` | Detached. [Source](../src/gnn/causal_temporal_graphsage.py#L73) |
| **`FeatureEncoder`** | Dense feature transform fitted strictly on the training split. [Source](../src/gnn/causal_temporal_graphsage.py#L77) |
| `FeatureEncoder.__init__(self, columns: list[str])` | Init. [Source](../src/gnn/causal_temporal_graphsage.py#L80) |
| `FeatureEncoder._one_hot()` | One hot. [Source](../src/gnn/causal_temporal_graphsage.py#L85) |
| `FeatureEncoder.fit(self, frame: pd.DataFrame)` | Fit. [Source](../src/gnn/causal_temporal_graphsage.py#L91) |
| `FeatureEncoder.transform(self, frame: pd.DataFrame)` | Transform. [Source](../src/gnn/causal_temporal_graphsage.py#L106) |
| `parse_args()` | Parse args. [Source](../src/gnn/causal_temporal_graphsage.py#L112) |
| `set_seed(seed: int)` | Set seed. [Source](../src/gnn/causal_temporal_graphsage.py#L140) |
| `columns_from_manifest(dataset: Path, node_frame: pd.DataFrame, edge_frame: pd.DataFrame)` | Columns from manifest. [Source](../src/gnn/causal_temporal_graphsage.py#L148) |
| `load_bank_frames(dataset: Path, bank: str, splits: tuple[str, ...]=SPLITS)` | Load bank frames. [Source](../src/gnn/causal_temporal_graphsage.py#L157) |
| `make_events(frame: pd.DataFrame, local_to_global: dict[int, int], edge_encoder: FeatureEncoder, origin: pd.Timestamp)` | Make events. [Source](../src/gnn/causal_temporal_graphsage.py#L183) |
| `build_bank_data(dataset: Path, bank: str, node_encoder: FeatureEncoder \| None=None, edge_encoder: FeatureEncoder \| None=None, splits: tuple[str, ...]=SPLITS)` | Build bank data. [Source](../src/gnn/causal_temporal_graphsage.py#L202) |
| `fit_shared_feature_encoders(dataset: Path, banks: tuple[str, ...]=BANKS)` | Fit one training-only schema so FedAvg clients have compatible tensors. [Source](../src/gnn/causal_temporal_graphsage.py#L235) |
| **`CausalTemporalGraphSAGE`** | GraphSAGE-style account memory updated only from earlier event batches. [Source](../src/gnn/causal_temporal_graphsage.py#L246) |
| `CausalTemporalGraphSAGE.__init__(self, node_features: int, edge_features: int, hidden: int, dropout: float)` | Init. [Source](../src/gnn/causal_temporal_graphsage.py#L249) |
| `CausalTemporalGraphSAGE.initial_state(self, static_features: Tensor)` | Initial state. [Source](../src/gnn/causal_temporal_graphsage.py#L263) |
| `CausalTemporalGraphSAGE.score_and_update(self, state: TemporalState, events: Events)` | Score and update. [Source](../src/gnn/causal_temporal_graphsage.py#L267) |
| `batches(events: Events, batch_size: int)` | Batches. [Source](../src/gnn/causal_temporal_graphsage.py#L296) |
| `epoch_sample_mask(labels: Tensor, negative_ratio: int, generator: torch.Generator)` | Select positives and a uniform stream-wide negative sample for one epoch. [Source](../src/gnn/causal_temporal_graphsage.py#L302) |
| `masked_loss(logits: Tensor, labels: Tensor, mask: Tensor, pos_weight: float=1.0)` | BCE for a preselected epoch sample within one chronological batch. [Source](../src/gnn/causal_temporal_graphsage.py#L323) |
| `train_temporal_epoch(model: CausalTemporalGraphSAGE, static: Tensor, events: Events, optimizer: torch.optim.Optimizer, sample_mask: Tensor, batch_size: int, tbptt_…)` | Train chronologically while retaining gradients across a bounded temporal window. [Source](../src/gnn/causal_temporal_graphsage.py#L332) |
| `score_stream(model: CausalTemporalGraphSAGE, state: TemporalState, events: Events, batch_size: int, check_cancel=None)` | Score stream. [Source](../src/gnn/causal_temporal_graphsage.py#L377) |
| `choose_threshold(labels: np.ndarray, probabilities: np.ndarray)` | Choose threshold. [Source](../src/gnn/causal_temporal_graphsage.py#L389) |
| `metric_block(labels: np.ndarray, probabilities: np.ndarray, threshold: float)` | Metric block. [Source](../src/gnn/causal_temporal_graphsage.py#L394) |
| `alert_budget_metrics(labels: np.ndarray, probabilities: np.ndarray, budgets: list[int])` | Alert budget metrics. [Source](../src/gnn/causal_temporal_graphsage.py#L405) |
| `platt_calibrate(validation_labels: np.ndarray, validation_probabilities: np.ndarray, probabilities: np.ndarray)` | Calibrate only from validation labels; no test labels enter fitting. [Source](../src/gnn/causal_temporal_graphsage.py#L419) |
| `train_bank(args: argparse.Namespace, bank: str, device: torch.device, node_encoder: FeatureEncoder \| None=None, edge_encoder: FeatureEncoder \| None=Non…)` | Train bank. [Source](../src/gnn/causal_temporal_graphsage.py#L430) |
| `main()` | Main. [Source](../src/gnn/causal_temporal_graphsage.py#L530) |

### `src/gnn/adaptive_continual_federated.py`

Risk/context replay, temporal update harmonization, optional research distillation and adaptive study training.

| Symbol | Purpose / source |
|---|---|
| `json_write(path: Path, value)` | Json write. [Source](../src/gnn/adaptive_continual_federated.py#L37) |
| `calendar_boundary(dataset: Path, bank: str)` | Calendar boundary. [Source](../src/gnn/adaptive_continual_federated.py#L43) |
| `development_fingerprint(dataset: Path)` | Fingerprint the actual CSV content, not gzip timestamps or test data. [Source](../src/gnn/adaptive_continual_federated.py#L49) |
| `load_development_clients(dataset: Path)` | Single development loader: the test split is deliberately unavailable. [Source](../src/gnn/adaptive_continual_federated.py#L64) |
| `fast_choose_threshold(labels: np.ndarray, scores: np.ndarray)` | Exactly the original 501-quantile F1 search, using cumulative counts. [Source](../src/gnn/adaptive_continual_federated.py#L74) |
| `risk_context_indices(history: Events, scores: np.ndarray, capacity: int, seed: int, hard_fraction: float=0.25, context_fraction: float=0.25)` | Bounded replay: positives, hard negatives, earlier endpoint context, coverage. [Source](../src/gnn/adaptive_continual_federated.py#L93) |
| `temporal_harmonized_average(states: list[dict], global_state: dict, strength: float=0.5, norm_cap: float=2.0)` | Equal-weight FedAvg for decoder/static; harmonize temporal deltas only. [Source](../src/gnn/adaptive_continual_federated.py#L159) |
| `distillation_epoch(model, static, events, optimizer, sample_mask, batch_size, tbptt_steps, teacher_logits, replay_mask, alpha)` | BCE plus class-balanced logit retention on completed-task replay only. [Source](../src/gnn/adaptive_continual_federated.py#L206) |
| `train_client(model, static, training, boundary, cfg, seed, check_cancel=lambda: None, progress=lambda *args: None)` | Train client. [Source](../src/gnn/adaptive_continual_federated.py#L248) |
| `validation(model, static, streams, batch_size)` | Validation. [Source](../src/gnn/adaptive_continual_federated.py#L304) |
| `parse_args()` | Parse args. [Source](../src/gnn/adaptive_continual_federated.py#L313) |
| `main()` | Main. [Source](../src/gnn/adaptive_continual_federated.py#L354) |

### `src/gnn/continual_temporal_graphsage.py`

Chronological event manipulation and original replay-based continual training.

| Symbol | Purpose / source |
|---|---|
| `parse_args()` | Parse args. [Source](../src/gnn/continual_temporal_graphsage.py#L22) |
| `subset(events: Events, mask: torch.Tensor)` | Subset. [Source](../src/gnn/continual_temporal_graphsage.py#L50) |
| `concat_chronological(first: Events, second: Events)` | Concat chronological. [Source](../src/gnn/continual_temporal_graphsage.py#L54) |
| `train_task(model, static, events, optimizer, cfg, seed: int)` | Train task. [Source](../src/gnn/continual_temporal_graphsage.py#L63) |
| `retention_metrics(model, static, events, batch_size: int)` | Retention metrics. [Source](../src/gnn/continual_temporal_graphsage.py#L72) |
| `replay_sample(history: Events, capacity: int, seed: int)` | Replay sample. [Source](../src/gnn/continual_temporal_graphsage.py#L77) |
| `run_bank(cfg, bank: str, device: torch.device, budgets: list[int], node_encoder, edge_encoder)` | Run bank. [Source](../src/gnn/continual_temporal_graphsage.py#L94) |
| `main()` | Main. [Source](../src/gnn/continual_temporal_graphsage.py#L151) |

### `src/gnn/federated_causal_temporal_graphsage.py`

Original corrected FedAvg/continual research experiment and diagnostics.

| Symbol | Purpose / source |
|---|---|
| `parse_args()` | Parse args. [Source](../src/gnn/federated_causal_temporal_graphsage.py#L29) |
| `make_optimizer(model, cfg)` | Make optimizer. [Source](../src/gnn/federated_causal_temporal_graphsage.py#L83) |
| `local_train(model, static, events, cfg, seed, global_parameters)` | Local train. [Source](../src/gnn/federated_causal_temporal_graphsage.py#L93) |
| `continual_local_train(model, static, events, cfg, seed)` | Match local CL: June training, then July plus a June-only replay sample. [Source](../src/gnn/federated_causal_temporal_graphsage.py#L155) |
| `fedavg(states: list[dict[str, torch.Tensor]], weights: list[int])` | Fedavg. [Source](../src/gnn/federated_causal_temporal_graphsage.py#L190) |
| `aggregation_weights(sample_counts: list[int], strategy: str)` | Aggregation weights. [Source](../src/gnn/federated_causal_temporal_graphsage.py#L198) |
| `update_l2_norm(local_state: dict[str, torch.Tensor], global_state: dict[str, torch.Tensor])` | Update l2 norm. [Source](../src/gnn/federated_causal_temporal_graphsage.py#L206) |
| `grouped_distance(left: dict[str, torch.Tensor], right: dict[str, torch.Tensor])` | Grouped distance. [Source](../src/gnn/federated_causal_temporal_graphsage.py#L211) |
| `pairwise_grouped_distances(states: list[dict[str, torch.Tensor]])` | Pairwise grouped distances. [Source](../src/gnn/federated_causal_temporal_graphsage.py#L219) |
| `interpolated_average(states, weights, global_state, server_lr: float, temporal_server_lr: float \| None)` | Interpolated average. [Source](../src/gnn/federated_causal_temporal_graphsage.py#L229) |
| `bank_validation_score(model, static, streams, batch_size: int)` | Bank validation score. [Source](../src/gnn/federated_causal_temporal_graphsage.py#L239) |
| `validation_scores(model, clients, batch_size: int)` | Validation scores. [Source](../src/gnn/federated_causal_temporal_graphsage.py#L247) |
| `final_evaluation(model, clients, batch_size: int, budgets: list[int], validation_only: bool)` | Final evaluation. [Source](../src/gnn/federated_causal_temporal_graphsage.py#L258) |
| `main()` | Main. [Source](../src/gnn/federated_causal_temporal_graphsage.py#L279) |

### `src/gnn/evaluate_frozen_temporal.py`

Historical explicit checkpoint evaluation utility.

| Symbol | Purpose / source |
|---|---|
| `parse_args()` | Parse args. [Source](../src/gnn/evaluate_frozen_temporal.py#L20) |
| `checkpoint_path(method: str, directory: Path, bank: str)` | Checkpoint path. [Source](../src/gnn/evaluate_frozen_temporal.py#L31) |
| `evaluate_model(model, static, streams, batch_size: int, budgets: list[int])` | Evaluate model. [Source](../src/gnn/evaluate_frozen_temporal.py#L39) |
| `main()` | Main. [Source](../src/gnn/evaluate_frozen_temporal.py#L55) |

### `src/gnn/run_temporal_multiseed.py`

Original multi-seed local-model experiment launcher.

| Symbol | Purpose / source |
|---|---|
| `parse_args()` | Parse args. [Source](../src/gnn/run_temporal_multiseed.py#L24) |
| `main()` | Main. [Source](../src/gnn/run_temporal_multiseed.py#L44) |

### `src/gnn/causal_tail_guard.py`

Separate experimental tail-ranking guard; not the promoted ensemble algorithm.

| Symbol | Purpose / source |
|---|---|
| `tail_ranking_risk(logits, labels, negative_ratio=20)` | Mean softplus(negative - positive) against the hardest training negatives. [Source](../src/gnn/causal_tail_guard.py#L16) |
| `training_task_risks(model, clients, batch_size)` | Each candidate rebuilds its own memory; July inherits its June memory. [Source](../src/gnn/causal_tail_guard.py#L35) |
| `select_guarded_step(old, proposed, evaluate, tolerance=0.05, steps=(1.0, 0.5, 0.25))` | Largest step with <= tolerance relative risk increase in EVERY valid task. [Source](../src/gnn/causal_tail_guard.py#L56) |
| `guarded_aggregation(model, clients, old, proposed, batch_size, tolerance)` | Guarded aggregation. [Source](../src/gnn/causal_tail_guard.py#L85) |

### `xai/src/grouped_features.py`

Exact empirical group-Shapley attribution with coherent joint amount/currency replacement.

| Symbol | Purpose / source |
|---|---|
| `explain_groups(predictor, row, training, *, background_size=32, seed=42, background_ids=None)` | Explain groups. [Source](../xai/src/grouped_features.py#L16) |

### `xai/src/ensemble_explainer.py`

Mean-probability ensemble predictor, member probabilities and exact feature Shapley utilities.

| Symbol | Purpose / source |
|---|---|
| `_sigmoid(logits: np.ndarray)` | Sigmoid. [Source](../xai/src/ensemble_explainer.py#L17) |
| `ensemble_logit_predictor(member_predictors: list[Callable[[pd.DataFrame], Iterable[float]]])` | Ensemble logit predictor. [Source](../xai/src/ensemble_explainer.py#L21) |
| `exact_interventional_shap(predict_logit: Callable[[pd.DataFrame], Iterable[float]], row: pd.Series, background: pd.DataFrame, features: list[str])` | Exact Shapley values for the empirical interventional background game. [Source](../xai/src/ensemble_explainer.py#L36) |
| `member_probability_details(member_predictors: list[Callable[[pd.DataFrame], Iterable[float]]], row: pd.DataFrame)` | Member probability details. [Source](../xai/src/ensemble_explainer.py#L82) |

### `xai/src/privacy_audit.py`

Historical XAI provenance auditing and redacted-copy export; does not establish formal DP.

| Symbol | Purpose / source |
|---|---|
| `redact_for_sharing(document: Any, *, key: bytes, pseudonymize_ids: bool=True, drop_keys: set[str] \| None=None)` | Remove detailed local evidence and pseudonymize identifier fields recursively. [Source](../xai/src/privacy_audit.py#L21) |
| `export_redacted_json(source: Path, destination: Path, *, key: bytes, policy: dict[str, Any] \| None=None)` | Write a redacted copy; the source local report is never modified. [Source](../xai/src/privacy_audit.py#L51) |
| `audit_run(root: Path, *, release_scope: str='local')` | Summarize provenance and flag local artifacts that should not be shared globally. [Source](../xai/src/privacy_audit.py#L63) |

### `scripts/verify_dashboard_workflow.py`

Repeatable HTTP acceptance: all-bank validation, XAI, local adaptation, selection and reloaded scoring.

| Symbol | Purpose / source |
|---|---|
| `main()` | Main. [Source](../scripts/verify_dashboard_workflow.py#L22) |

### `scripts/export_federation_schema.py`

Exports the shared synthetic-reference training-only preprocessing contract.

| Symbol | Purpose / source |
|---|---|
| `spec(encoder)` | Spec. [Source](../scripts/export_federation_schema.py#L9) |
| `main()` | Main. [Source](../scripts/export_federation_schema.py#L22) |

### `scripts/evaluate_seed_ensemble.py`

Original ensemble freeze/evaluation script; preserves completed September evidence.

| Symbol | Purpose / source |
|---|---|
| `digest(path)` | Digest. [Source](../scripts/evaluate_seed_ensemble.py#L23) |
| `mean_probabilities(predictions)` | Mean probabilities. [Source](../scripts/evaluate_seed_ensemble.py#L27) |
| `score(entries, include_test=False, thresholds=None)` | Score. [Source](../scripts/evaluate_seed_ensemble.py#L34) |
| `main()` | Main. [Source](../scripts/evaluate_seed_ensemble.py#L65) |

### `streaming/test_federation.py`

Real local Kafka/PyTorch three-bank ensemble acceptance check.

| Symbol | Purpose / source |
|---|---|
| `main()` | Main. [Source](../streaming/test_federation.py#L15) |

### `streaming/test_local_transfer.py`

Real Kafka checkpoint-file transfer and signed receipt acceptance check.

| Symbol | Purpose / source |
|---|---|
| `request(base, path, data=None, token=None)` | Request. [Source](../streaming/test_local_transfer.py#L15) |
| `main()` | Main. [Source](../streaming/test_local_transfer.py#L26) |

### `streaming/test_recovery.py`

Real Kafka retry/receipt recovery acceptance check.

| Symbol | Purpose / source |
|---|---|
| `main()` | Main. [Source](../streaming/test_recovery.py#L17) |

## Historical and supporting material

Other scripts under `scripts/` prepare/audit data or reproduce the named research study. Their matching reports under `docs/` describe those experimental protocols. The dashboard does not call every historical experiment when launched. Standalone `xai/serve_dashboard.py` and generated `xai/outputs/` reports are earlier XAI presentation tools; the integrated dashboard uses `streaming/app/explanations.py` with the selected current replay model.

Checkpoints in `artifacts/research_adaptive_fcl/warm_start/federated/context_harmonized/` are the three reference members. `artifacts/research_seed_ensemble/FREEZE.json` fixes hashes and thresholds; `exploratory_september/metrics.json` is the saved headline result. `artifacts/final_evaluation/` contains earlier baseline evidence. None of these original files is overwritten by normal dashboard training.

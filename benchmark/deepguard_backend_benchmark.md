# DeepGuard Backend Benchmark

15 rigorous questions targeting the DeepGuard Integrated Backend (Express Gateway + FastAPI/TFLite ML Engine) and Supabase database / storage integration.

> **Evaluation Rule:** Every question specifies concrete `required_evidence`, `expected_symbols`, `expected_answer_points`, and `difficulty` levels (L1–L5). A rigorous agent evaluation must grade answers against these ground-truth expectations.

---

## DGB01 — Architecture (L4)
**Question:** Trace how user authentication, JWT access tokens, refresh tokens, and device sessions are created, stored, and rotated in the backend. Where are refresh tokens persisted in Supabase, how is the device fingerprint calculated, and how does the server prevent token reuse or replay attacks?

- **Category:** `architecture`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L4` (Files: 5, Hops: 4, Concepts: 5)
- **Repository:** `deepguard_backend` (Commit: `81367569881a`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `True` | **Verification:** `True`

**Required Evidence Files:**
- `app/Deep-Guard-Backend/controllers/authcontroller.js`
- `app/Deep-Guard-Backend/utils/authHelpers.js`
- `app/Deep-Guard-Backend/middleware/authenticateToken.js`

**Supporting Evidence:**
- `app/Deep-Guard-Backend/config/supabase.js`
- `app/Deep-Guard-Backend/routes/auth.js`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `app/Deep-Guard-Backend/controllers/trial.js`
- `app/Deep-Guard-Backend/routes/userRoutes.js`

**Expected Symbols:** `createSession, signup, login, refresh, authenticateToken, generateTokens`

**Expected Concepts:** `JWT dual-token architecture, Supabase user_sessions table, device fingerprinting hash, HttpOnly cookie storage, refresh token rotation`

**Expected Tool Capabilities:** `repository_search, symbol_lookup, file_read, graph_traversal`

**Expected Answer Points:**
1. Login/signup validates credentials in authcontroller.js and generates a short-lived access token and long-lived refresh token via authHelpers.js.
1. A session record is created in Supabase 'user_sessions' storing the hashed refresh token, user ID, IP address, user-agent, and device fingerprint.
1. Tokens are delivered to the client via secure, HttpOnly cookies (accessToken and refreshToken).
1. On /refresh, the backend queries Supabase for the active session, validates the refresh token signature, invalidates the old token, and issues a new token pair (rotation).
1. authenticateToken.js middleware extracts the token from cookies or Authorization header and verifies it with jwt.verify(token, JWT_SECRET).

**Expected Answer Structure:**
- credential verification and token generation
- Supabase user_sessions storage and schema
- cookie delivery and security flags
- refresh token rotation mechanism
- middleware verification and replay protection

**Known Traps & Failure Modes:**
- Assuming refresh tokens are stored only in memory or Redis instead of Supabase user_sessions table
- Confusing middleware/auth.js with middleware/authenticateToken.js

---

## DGB02 — Security (L3)
**Question:** How does DeepGuard permit users to test deepfake analysis without creating an account ('Try Without Account') while preventing abuse? Trace how device fingerprints and IP records are generated, validated in Supabase, and how expired trials are cleaned up.

- **Category:** `security`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L3` (Files: 4, Hops: 3, Concepts: 4)
- **Repository:** `deepguard_backend` (Commit: `81367569881a`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `True`

**Required Evidence Files:**
- `app/Deep-Guard-Backend/controllers/trial.js`
- `app/Deep-Guard-Backend/middleware/trial.js`
- `app/Deep-Guard-Backend/routes/trial.analyze.js`

**Supporting Evidence:**
- `app/Deep-Guard-Backend/routes/trial.js`
- `app/Deep-Guard-Backend/routes/trail.status.js`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `app/Deep-Guard-Backend/controllers/analysisController.js`

**Expected Symbols:** `joinTrial, cleanupExpiredTrials, getDeviceFingerprint, checkTrialEligibility`

**Expected Concepts:** `anonymous trial token, device fingerprinting, trial rate-limiting in Supabase, scheduled trial cleanup`

**Expected Tool Capabilities:** `repository_search, file_read, cross_file_trace`

**Expected Answer Points:**
1. Anonymous trial entry generates a device fingerprint from IP, User-Agent, and headers.
1. The controller queries Supabase 'trials' table to verify whether this fingerprint or IP has already exhausted its trial allowance.
1. If eligible, a short-lived trial token is issued permitting a limited analysis (e.g. 1 video/image with capped frames).
1. trial.analyze.js routes the analysis request through trial validation middleware before delegating to the ML service.
1. cleanupExpiredTrials function periodically runs to purge or flag expired trial entries in Supabase.

**Expected Answer Structure:**
- device fingerprint creation
- Supabase eligibility verification
- trial token generation and rate limit bounds
- delegation to trial analysis route
- expired session purge logic

**Known Traps & Failure Modes:**
- Assuming trial status uses Redis TTL instead of Supabase database rows and cleanupExpiredTrials
- Overlooking trial.analyze.js route which separates trial analysis from standard user analysis

---

## DGB03 — Execution Flow (L5)
**Question:** When a user uploads a video file for deepfake inspection, trace the complete request from Express upload middleware through file storage, delegation to the Python FastAPI ML Engine, and the receipt of prediction results. Where is the file temporarily buffered, and what happens if the ML engine fails?

- **Category:** `execution_flow`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L5` (Files: 6, Hops: 5, Concepts: 5)
- **Repository:** `deepguard_backend` (Commit: `81367569881a`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `True` | **Verification:** `True`

**Required Evidence Files:**
- `app/Deep-Guard-Backend/routes/analysis.js`
- `app/Deep-Guard-Backend/controllers/analysisController.js`
- `app/Deep-Guard-Backend/routes/ml-service.js`
- `app/Deep-Guard-ML-Engine/app/routes/video_detection.py`

**Supporting Evidence:**
- `app/Deep-Guard-Backend/middleware/fileupload.js`
- `app/Deep-Guard-Backend/services/analysisService.js`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `app/Deep-Guard-Backend/routes/analysis-image-upload.js`
- `app/Deep-Guard-ML-Engine/app/routes/image_detection.py`

**Expected Symbols:** `uploadFile, analyzeVideo, predict_video, forwardToMLService`

**Expected Concepts:** `multipart/form-data upload, temporary disk/memory buffer, HTTP form-data proxy to FastAPI, Supabase analysis record status transitions, error boundary and cleanup`

**Expected Tool Capabilities:** `repository_search, file_read, cross_file_trace, graph_traversal`

**Expected Answer Points:**
1. Client posts multipart video to Express /analysis route where fileupload.js middleware validates file size and mime type.
1. analysisController.js creates an initial record in Supabase 'analyses' table with status 'processing'.
1. The file stream is forwarded via axios/form-data in ml-service.js to the FastAPI ML Engine at POST /detect/deepfake/video.
1. The ML engine accepts UploadFile, extracts frames, performs TFLite inference, and returns prediction metrics and zipped annotated frames.
1. analysisController.js updates Supabase with confidence scores and status 'completed'; on ML failure, status is set to 'failed' with error_message.

**Expected Answer Structure:**
- Express upload ingestion and middleware validation
- Supabase initial record creation
- IPC forwarding to FastAPI ML Engine
- FastAPI response consumption
- database status update and error recovery

**Known Traps & Failure Modes:**
- Confusing video analysis routing with image analysis routing (ml-service.js vs ml-service-images.js)
- Assuming files are directly stored in S3/Azure Blob before inference rather than forwarded via multipart IPC

---

## DGB04 — Api Contract (L3)
**Question:** Contrast the image analysis pipeline with the video pipeline. Trace how analysis-image-upload.js and ml-service-images.js route image data to the FastAPI ML Engine's /detect/deepfake/images endpoint, and where image analysis records are committed to Supabase.

- **Category:** `api_contract`
- **Answer Type:** `comparison`
- **Difficulty:** `L3` (Files: 4, Hops: 3, Concepts: 3)
- **Repository:** `deepguard_backend` (Commit: `81367569881a`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `app/Deep-Guard-Backend/routes/analysis-image-upload.js`
- `app/Deep-Guard-Backend/routes/ml-service-images.js`
- `app/Deep-Guard-ML-Engine/app/routes/image_detection.py`

**Supporting Evidence:**
- `app/Deep-Guard-Backend/controllers/analysisController.js`
- `app/Deep-Guard-Backend/config/supabase.js`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `app/Deep-Guard-Backend/routes/ml-service.js`
- `app/Deep-Guard-ML-Engine/app/routes/video_detection.py`

**Expected Symbols:** `predict_image, uploadImage, forwardImageToML`

**Expected Concepts:** `single-frame static inference, dedicated image router, FastAPI FileResponse vs JSON response, Supabase image analysis persistence`

**Expected Tool Capabilities:** `repository_search, file_read, symbol_lookup`

**Expected Answer Points:**
1. Image analysis uses dedicated routes (analysis-image-upload.js and ml-service-images.js) separate from video analysis.
1. The request is forwarded to FastAPI endpoint POST /detect/deepfake/images instead of /detect/deepfake/video.
1. Image processing extracts single facial crops without multi-frame temporal tracking or video decoder overhead.
1. The ML response returns confidence and annotated image directly.
1. Results are persisted in Supabase with image-specific attributes (single confidence score, no frame array).

**Expected Answer Structure:**
- image route separation and entry points
- FastAPI endpoint contrast (/detect/deepfake/images)
- processing pipeline differences (single crop vs temporal frames)
- Supabase record structure contrast

**Known Traps & Failure Modes:**
- Assuming both video and image go through the same ml-service.js file
- Missing that FastAPI has two separate route files: image_detection.py and video_detection.py

---

## DGB05 — Architecture (L4)
**Question:** Inside the Python ML Engine, how is the TensorFlow Lite deepfake model loaded and invoked? Trace how faces are extracted and tracked across video frames before being passed to the classifier.

- **Category:** `architecture`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L4` (Files: 5, Hops: 4, Concepts: 5)
- **Repository:** `deepguard_backend` (Commit: `81367569881a`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `True` | **Verification:** `False`

**Required Evidence Files:**
- `app/Deep-Guard-ML-Engine/app/services/model.py`
- `app/Deep-Guard-ML-Engine/app/utils/face_extractor.py`
- `app/Deep-Guard-ML-Engine/app/utils/face_tracker.py`
- `app/Deep-Guard-ML-Engine/app/services/video_preprocessor.py`

**Supporting Evidence:**
- `app/Deep-Guard-ML-Engine/app/routes/video_detection.py`
- `app/Deep-Guard-ML-Engine/app/config/config.py`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `app/Deep-Guard-ML-Engine/Model Builder Code/Model_Builder.py`

**Expected Symbols:** `FaceExtractor, FaceTracker3D, VideoPreprocessor, predict, _track_yunet, _track_mediapipe`

**Expected Concepts:** `tflite.Interpreter, input/output tensor allocation, face crop normalization (224x224/256x256), YuNet/MediaPipe fallback tracking, frame sampling rate`

**Expected Tool Capabilities:** `repository_search, symbol_lookup, file_read, graph_traversal`

**Expected Answer Points:**
1. model.py initializes tflite.Interpreter pointing to deepfake_detector.tflite and allocates tensors.
1. VideoPreprocessor samples frames from the input video based on requested frame count (e.g. 30–50 frames).
1. FaceTracker3D / FaceExtractor detects faces using primary YuNet tracker with MediaPipe and Haar cascade fallbacks.
1. Cropped face regions are resized, normalized to [0, 1] float tensors, and reshaped to model input dimensions.
1. interpreter.set_tensor and interpreter.invoke execute inference, returning deepfake probability per frame.

**Expected Answer Structure:**
- TFLite interpreter initialization and tensor details
- video frame sampling via VideoPreprocessor
- face detection and 3D tracker fallbacks
- crop preprocessing and normalization
- model invocation and probability calculation

**Known Traps & Failure Modes:**
- Citing training scripts in 'Model Builder Code/' instead of active inference code in 'app/services/model.py'
- Assuming standard heavy PyTorch or TensorFlow model instead of lightweight TFLite runtime

---

## DGB06 — Data Flow (L3)
**Question:** How does the ML Engine package prediction results and annotated frames back to the caller? Trace how bounding boxes and confidence metrics are overlaid onto video frames and how the output zip/response is constructed and returned.

- **Category:** `data_flow`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L3` (Files: 4, Hops: 3, Concepts: 4)
- **Repository:** `deepguard_backend` (Commit: `81367569881a`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `app/Deep-Guard-ML-Engine/app/utils/annotate_images.py`
- `app/Deep-Guard-ML-Engine/app/services/video_saver.py`
- `app/Deep-Guard-ML-Engine/app/routes/video_detection.py`

**Supporting Evidence:**
- `app/Deep-Guard-ML-Engine/app/utils/video_processor.py`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `app/Deep-Guard-ML-Engine/app/services/image_saver.py`

**Expected Symbols:** `annotate_frame, save_annotated_video, predict_video, create_zip_archive`

**Expected Concepts:** `OpenCV bounding box annotation, color-coded confidence labels, zip archive creation, FastAPI FileResponse with custom headers`

**Expected Tool Capabilities:** `repository_search, file_read, symbol_lookup`

**Expected Answer Points:**
1. annotate_images.py draws colored bounding boxes and probability labels (green for real, red for deepfake) using OpenCV.
1. video_saver.py writes annotated frames to a temporary directory.
1. A zip archive containing the annotated frames and summary metadata is created on disk.
1. video_detection.py streams the zip archive back using FastAPI FileResponse with media_type application/zip.
1. Custom HTTP headers pass overall confidence score and frame counts back to the Express gateway.

**Expected Answer Structure:**
- frame annotation with OpenCV
- saving frames to temporary structure
- zip packaging mechanism
- FastAPI FileResponse transmission and headers

**Known Traps & Failure Modes:**
- Assuming output is returned purely as JSON without binary frame zip archive
- Confusing video_saver.py with image_saver.py

---

## DGB07 — Debugging (L2)
**Question:** How does the ML Engine prevent disk exhaustion from uploaded and processed video files? Trace the execution of background cleanup tasks, where files are stored temporarily on disk, and how cleanup errors are handled.

- **Category:** `debugging`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L2` (Files: 3, Hops: 2, Concepts: 3)
- **Repository:** `deepguard_backend` (Commit: `81367569881a`)
- **Multi-Hop Required:** `False` | **Graph Reasoning:** `False` | **Verification:** `True`

**Required Evidence Files:**
- `app/Deep-Guard-ML-Engine/app/utils/delayed_cleanup.py`
- `app/Deep-Guard-ML-Engine/app/routes/video_detection.py`

**Supporting Evidence:**
- `app/Deep-Guard-ML-Engine/app/config/config.py`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `app/Deep-Guard-Backend/controllers/trial.js`

**Expected Symbols:** `delayed_cleanup, BackgroundTasks, predict_video`

**Expected Concepts:** `FastAPI BackgroundTasks, delayed file deletion, shutil.rmtree / os.remove, temporary directory lifecycle`

**Expected Tool Capabilities:** `repository_search, file_read, symbol_lookup`

**Expected Answer Points:**
1. Uploaded videos and extracted frames are stored in temporary directory paths specified in config.py.
1. FastAPI BackgroundTasks parameter is injected into predict_video route.
1. background_tasks.add_task(delayed_cleanup, [paths], delay_seconds) schedules asynchronous deletion after the response finishes streaming.
1. delayed_cleanup sleeps for a short buffer time to ensure streaming completion, then recursively removes temporary folders with shutil.rmtree.
1. Exceptions during cleanup are logged without interrupting the client connection.

**Expected Answer Structure:**
- temporary storage locations
- FastAPI BackgroundTasks injection
- delayed_cleanup implementation and sleep delay
- safe filesystem deletion and exception handling

**Known Traps & Failure Modes:**
- Assuming a Celery/Redis queue handles cleanup when it is actually native FastAPI BackgroundTasks
- Assuming files are deleted immediately inside the request body before FileResponse finishes

---

## DGB08 — Architecture (L2)
**Question:** Trace how the Supabase client is initialized in the Node.js backend. Which tables are read and written during an analysis lifecycle, and what credentials/service keys are required?

- **Category:** `architecture`
- **Answer Type:** `explanation`
- **Difficulty:** `L2` (Files: 3, Hops: 2, Concepts: 3)
- **Repository:** `deepguard_backend` (Commit: `81367569881a`)
- **Multi-Hop Required:** `False` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `app/Deep-Guard-Backend/config/supabase.js`
- `app/Deep-Guard-Backend/controllers/analysisController.js`

**Supporting Evidence:**
- `app/Deep-Guard-Backend/services/analysisService.js`
- `app/Deep-Guard-Backend/controllers/authcontroller.js`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `app/Deep-Guard-ML-Engine/app/config/config.py`

**Expected Symbols:** `createClient, supabase, uploadFile`

**Expected Concepts:** `@supabase/supabase-js createClient, SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY, analyses table schema, user_sessions table`

**Expected Tool Capabilities:** `repository_search, file_read`

**Expected Answer Points:**
1. config/supabase.js imports createClient from @supabase/supabase-js.
1. Initializes client using process.env.SUPABASE_URL and process.env.SUPABASE_SERVICE_ROLE_KEY (or anon key).
1. Exported supabase singleton is imported across controllers.
1. During analysis lifecycle, it inserts a new row into 'analyses' with user_id, filename, status='processing'.
1. Upon completion, updates 'analyses' with confidence_score, is_deepfake, frames_analyzed, and frame_wise_confidences.

**Expected Answer Structure:**
- client initialization and required environment variables
- singleton export pattern
- tables touched during analysis ('analyses', 'user_sessions')
- record lifecycle from creation to completion

**Known Traps & Failure Modes:**
- Claiming Prisma, TypeORM, or Mongoose is used instead of the official Supabase JavaScript SDK
- Assuming ML engine connects directly to Supabase (only the Express backend touches Supabase)

---

## DGB09 — Security (L3)
**Question:** Trace the end-to-end password reset flow. How is the OTP generated, what email transport service dispatches it, where is the verification token stored, and how does the backend prevent brute-force OTP attempts?

- **Category:** `security`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L3` (Files: 4, Hops: 3, Concepts: 4)
- **Repository:** `deepguard_backend` (Commit: `81367569881a`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `True`

**Required Evidence Files:**
- `app/Deep-Guard-Backend/controllers/authcontroller.js`
- `app/Deep-Guard-Backend/utils/authHelpers.js`
- `app/Deep-Guard-Backend/routes/auth.js`

**Supporting Evidence:**
- `app/Deep-Guard-Backend/utils/helpers.js`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `app/Deep-Guard-Backend/controllers/support.js`

**Expected Symbols:** `sendResetOtp, resetPassword, generateOTP, sendEmail`

**Expected Concepts:** `6-digit numeric OTP generation, Nodemailer/SMTP transport, Supabase password_resets table with expiry, bcrypt password hashing`

**Expected Tool Capabilities:** `repository_search, file_read, symbol_lookup`

**Expected Answer Points:**
1. sendResetOtp in authcontroller.js verifies user exists in Supabase by email.
1. Generates a 6-digit random OTP and stores it in Supabase with a 10-15 minute expiration timestamp.
1. Dispatches OTP to user email using nodemailer configured with SMTP environment variables.
1. resetPassword verifies the submitted OTP against the stored entry and checks expiration.
1. Hashes the new password with bcrypt and updates the user table, invalidating existing sessions.

**Expected Answer Structure:**
- email validation and user lookup
- OTP generation and expiration persistence in Supabase
- SMTP dispatch via nodemailer
- OTP verification and bcrypt password update

**Known Traps & Failure Modes:**
- Assuming SendGrid/Resend API is used if Nodemailer SMTP is configured
- Assuming OTP is stored in JWT rather than database table with timestamp

---

## DGB10 — Cross File Reasoning (L2)
**Question:** How does DeepGuard fetch repository statistics and contributor information for display? Trace the GitHub API integration in github.js, including rate-limit header handling and payload transformation.

- **Category:** `cross_file_reasoning`
- **Answer Type:** `explanation`
- **Difficulty:** `L2` (Files: 3, Hops: 2, Concepts: 3)
- **Repository:** `deepguard_backend` (Commit: `81367569881a`)
- **Multi-Hop Required:** `False` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `app/Deep-Guard-Backend/controllers/github.js`
- `app/Deep-Guard-Backend/routes/github.js`

**Supporting Evidence:**
- `app/Deep-Guard-Backend/server.js`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `app/Deep-Guard-Backend/controllers/support.js`

**Expected Symbols:** `getRepoStats, getContributors, getPulls, getGithubHeaders`

**Expected Concepts:** `GitHub REST API v3, authorization headers with GITHUB_TOKEN, contributor commit aggregations, pull request filtering`

**Expected Tool Capabilities:** `repository_search, file_read, symbol_lookup`

**Expected Answer Points:**
1. github.js controller defines endpoints for repository stats, contributors, and pull requests.
1. getGithubHeaders sets Accept: application/vnd.github.v3+json and Authorization Bearer using process.env.GITHUB_TOKEN if present.
1. Calls api.github.com/repos/{owner}/{repo}/contributors to get contributor avatars, commit counts, and profile links.
1. Aggregates stars, forks, and open issues into a unified statistics payload.
1. Returns clean JSON payload formatted for the frontend GithubRepoCard and ContributorList components.

**Expected Answer Structure:**
- route and controller structure
- GitHub API authentication headers
- external endpoints called
- data aggregation and payload formatting

**Known Traps & Failure Modes:**
- Assuming GitHub GraphQL API is used rather than REST API endpoints
- Assuming contributor data is stored permanently in Supabase rather than queried dynamically

---

## DGB11 — Architecture (L1)
**Question:** What is the purpose of the Supabase keep-alive edge function in the repository? Trace how it is implemented, what endpoints or services it pings, and how cold-start delays are mitigated.

- **Category:** `architecture`
- **Answer Type:** `explanation`
- **Difficulty:** `L1` (Files: 2, Hops: 1, Concepts: 2)
- **Repository:** `deepguard_backend` (Commit: `81367569881a`)
- **Multi-Hop Required:** `False` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `app/Deep-Guard-Backend/supabase/functions/keep-alive/index.ts`

**Supporting Evidence:**
- `render.yaml`
- `app/Deep-Guard-Backend/server.js`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `app/Deep-Guard-Backend/controllers/support.js`

**Expected Symbols:** `serve, Deno.serve`

**Expected Concepts:** `Supabase Deno Edge Function, free-tier hosting cold-start prevention, scheduled health ping, HTTP fetch invocation`

**Expected Tool Capabilities:** `repository_search, file_read`

**Expected Answer Points:**
1. Located at supabase/functions/keep-alive/index.ts written in TypeScript for Deno runtime.
1. Designed to prevent free-tier Render or Supabase instances from spinning down due to inactivity.
1. Performs periodic HTTP GET requests to the backend /health or base URL.
1. Returns 200 OK status with timestamp and execution metrics.

**Expected Answer Structure:**
- edge function location and Deno runtime
- cold-start mitigation objective
- ping target and response handling

**Known Traps & Failure Modes:**
- Confusing Supabase Edge Function (Deno) with Node.js Express server routes

---

## DGB12 — Debugging (L2)
**Question:** How are runtime exceptions captured across the Express application? Trace errorHandler.js and logger.js to explain how unhandled rejections, file validation errors, and database errors are standardized in API responses.

- **Category:** `debugging`
- **Answer Type:** `architecture`
- **Difficulty:** `L2` (Files: 3, Hops: 2, Concepts: 3)
- **Repository:** `deepguard_backend` (Commit: `81367569881a`)
- **Multi-Hop Required:** `False` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `app/Deep-Guard-Backend/middleware/errorHandler.js`
- `app/Deep-Guard-Backend/middleware/logger.js`

**Supporting Evidence:**
- `app/Deep-Guard-Backend/utils/logger.js`
- `app/Deep-Guard-Backend/server.js`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `app/Deep-Guard-Backend/middleware/auth.js`

**Expected Symbols:** `errorHandler, loggerMiddleware`

**Expected Concepts:** `Express 4-argument error middleware (err, req, res, next), custom AppError / status mapping, sanitized client error responses, structured console logging`

**Expected Tool Capabilities:** `repository_search, file_read, symbol_lookup`

**Expected Answer Points:**
1. errorHandler.js is mounted as the final middleware in server.js with 4 parameters: (err, req, res, next).
1. Checks err.statusCode or defaults to 500 Internal Server Error.
1. Logs error details, stack traces, and request context via logger.js.
1. Formats response as JSON: { success: false, message: err.message, ...(isDev && { stack: err.stack }) }.
1. Catches multer file upload errors (e.g. LIMIT_FILE_SIZE) and formats them cleanly with 400 status.

**Expected Answer Structure:**
- middleware registration and signature
- status code resolution
- logging behavior
- client JSON response format and environment-conditional stack trace

**Known Traps & Failure Modes:**
- Assuming Winston or Morgan is used if custom logger.js is implemented
- Overlooking that errorHandler must be registered after all route handlers

---

## DGB13 — Data Flow (L1)
**Question:** Trace how bug reports and support requests submitted by users are processed. Which controller handles the request, what validation is performed on attachments, and where are reports dispatched?

- **Category:** `data_flow`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L1` (Files: 2, Hops: 1, Concepts: 2)
- **Repository:** `deepguard_backend` (Commit: `81367569881a`)
- **Multi-Hop Required:** `False` | **Graph Reasoning:** `False` | **Verification:** `False`

**Required Evidence Files:**
- `app/Deep-Guard-Backend/controllers/support.js`
- `app/Deep-Guard-Backend/routes/support.js`

**Supporting Evidence:**
- `app/Deep-Guard-Backend/utils/helpers.js`
- `app/Deep-Guard-Backend/server.js`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `app/Deep-Guard-Backend/controllers/github.js`

**Expected Symbols:** `sendBugReport`

**Expected Concepts:** `support route handling, Nodemailer email notification, attachment validation, ticket payload structure`

**Expected Tool Capabilities:** `repository_search, file_read`

**Expected Answer Points:**
1. support.js controller handles POST /support/bug-report (or similar route).
1. Validates user email, issue description, severity, and optional screenshot/log attachments.
1. Dispatches an email notification to the administrative support inbox using the configured email transporter.
1. Optionally logs or persists the ticket reference and returns a confirmation JSON response to the user.

**Expected Answer Structure:**
- route and controller entry point
- request validation
- email dispatch mechanism
- client response format

**Known Traps & Failure Modes:**
- Confusing customer support tickets with GitHub issues integration in github.js

---

## DGB14 — Configuration (L4)
**Question:** How are the Node.js Express API and the Python FastAPI ML Engine configured to communicate in Docker? Trace service networking, port bindings, shared volumes (if any), and startup scripts.

- **Category:** `configuration`
- **Answer Type:** `architecture`
- **Difficulty:** `L4` (Files: 4, Hops: 3, Concepts: 4)
- **Repository:** `deepguard_backend` (Commit: `81367569881a`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `False` | **Verification:** `True`

**Required Evidence Files:**
- `docker-compose.yml`
- `app/Deep-Guard-Backend/Dockerfile`
- `app/Deep-Guard-ML-Engine/Dockerfile`

**Supporting Evidence:**
- `start.sh`
- `render.yaml`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `app/Deep-Guard-Backend/package.json`

**Expected Concepts:** `multi-container Docker network, Express service (port 5000/8080), FastAPI ML Engine (port 8000), ML_SERVICE_URL environment variable, container health dependencies`

**Expected Tool Capabilities:** `repository_search, file_read`

**Expected Answer Points:**
1. docker-compose.yml orchestrates two primary services: the Node.js Express backend and the Python ML Engine.
1. The Express service exposes port 5000 (or mapped host port) while the ML Engine runs on internal port 8000.
1. The Express service is configured with ML_SERVICE_URL=http://ml-engine:8000 pointing to the Docker service name.
1. start.sh or Dockerfile entrypoints ensure the ML service starts and compiles TFLite requirements before traffic routes.
1. render.yaml provides deployment specifications for unified deployment on Render platform.

**Expected Answer Structure:**
- Docker compose service definitions
- port mapping and internal container networking
- environment variable configuration (ML_SERVICE_URL)
- container build stages and startup order

**Known Traps & Failure Modes:**
- Assuming both run inside a single monolith process rather than separate polyglot containers
- Missing the service hostname resolution in Docker network (ml-engine:8000 vs localhost:8000)

---

## DGB15 — Cross File Reasoning (L5)
**Question:** Trace a single video analysis request from the moment an authenticated client posts multipart video data to the Express gateway, through token validation, ML delegation, frame sampling (50 frames), face bounding box extraction, TFLite inference, Supabase database record insertion, and final response transmission. Identify every point where latency or failure could occur.

- **Category:** `cross_file_reasoning`
- **Answer Type:** `execution_trace`
- **Difficulty:** `L5` (Files: 8, Hops: 7, Concepts: 7)
- **Repository:** `deepguard_backend` (Commit: `81367569881a`)
- **Multi-Hop Required:** `True` | **Graph Reasoning:** `True` | **Verification:** `True`

**Required Evidence Files:**
- `app/Deep-Guard-Backend/server.js`
- `app/Deep-Guard-Backend/middleware/authenticateToken.js`
- `app/Deep-Guard-Backend/controllers/analysisController.js`
- `app/Deep-Guard-Backend/routes/ml-service.js`
- `app/Deep-Guard-ML-Engine/app/routes/video_detection.py`
- `app/Deep-Guard-ML-Engine/app/services/model.py`
- `app/Deep-Guard-Backend/config/supabase.js`

**Supporting Evidence:**
- `app/Deep-Guard-Backend/middleware/fileupload.js`
- `app/Deep-Guard-ML-Engine/app/utils/face_extractor.py`
- `app/Deep-Guard-ML-Engine/app/utils/delayed_cleanup.py`

**Decoy / Negative Files (Must Not Confuse Agent):**
- `app/Deep-Guard-Backend/routes/analysis-image-upload.js`
- `app/Deep-Guard-ML-Engine/Model Builder Code/Model_Builder.py`

**Expected Symbols:** `authenticateToken, uploadFile, forwardToMLService, predict_video, predict`

**Expected Concepts:** `full-stack architectural hop, JWT cookie extraction, multipart streaming latency, video decoding bottlenecks, TFLite tensor execution, database consistency, failure modes at each boundary`

**Expected Tool Capabilities:** `repository_search, symbol_lookup, file_read, graph_traversal, cross_file_trace`

**Expected Answer Points:**
1. Hop 1: Express server.js receives multipart POST request; authenticateToken.js extracts JWT from cookie/header and validates signature (failure point: token expired 401).
1. Hop 2: fileupload.js buffers video; analysisController.js writes initial row to Supabase 'analyses' table with status 'processing' (failure point: DB connection error).
1. Hop 3: ml-service.js forwards stream to FastAPI /detect/deepfake/video (failure point: network timeout / IPC disconnection 502).
1. Hop 4: FastAPI VideoPreprocessor decodes video and samples 50 frames; FaceTracker3D/YuNet isolates face crops (failure point: corrupted video codec or 0 faces detected).
1. Hop 5: model.py invokes TFLite interpreter across normalized face tensors; annotates frames and compresses into zip (failure point: out of memory OOM).
1. Hop 6: FastAPI returns FileResponse with zip + header metrics; background_tasks triggers delayed_cleanup.
1. Hop 7: Express updates Supabase with confidence scores, sets status 'completed', and sends final JSON response to client.

**Expected Answer Structure:**
- entry point and auth validation
- Supabase initial record creation
- IPC network stream forwarding
- computer vision extraction & TFLite inference
- artifact packaging & response streaming
- database finalization
- systemic latency & failure mode enumeration

**Known Traps & Failure Modes:**
- Missing the IPC boundary between Node.js and Python processes
- Forgetting that background cleanup happens after the response is returned
- Omitting the initial Supabase 'processing' status write before the ML call

---

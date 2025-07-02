import apiClient from './apiClient.js';

// --- GLOBAL STATE ---
let allTranscripts = [];
let editMode = false;
let audioHighlightInterval = null;
let pendingDeleteFilename = null;

// --- UI & UTILITY ---
function showToast(message, type = "info") { const bg = { success: "#4BB543", error: "#ff5c5c", info: "#3498db" }[type] || "#333"; Toastify({ text: message, duration: 3000, gravity: "top", position: "right", style: { background: bg } }).showToast(); }
function toggleDarkMode() { document.body.classList.toggle("dark"); localStorage.setItem("prefDark", document.body.classList.contains("dark")); }
function toggleProfile() { const profileBox = document.getElementById("profileBox"), overlay = document.getElementById("profileOverlay"), isVisible = profileBox.style.display === "block"; profileBox.style.display = isVisible ? "none" : "block"; if (overlay) overlay.style.display = isVisible ? "none" : "block"; }
function toggleAnalytics() { showToast("Analytics not implemented yet.", "info"); }

// --- AUTH & USER ---
// --- USER LOGIN ---
// Handles the user login form submission.
async function login() {
    const email = document.getElementById("loginEmail").value;
    const password = document.getElementById("loginPassword").value;

    // --- Input Validation ---
    if (!email || !password) {
        return showToast("Please enter both email and password.", "error");
    }

    try {
        // Use apiClient.post. Note that '/api/auth/login' might need to be '/api/auth/token'
        // depending on your backend router, but based on your original code, '/api/auth/login' is likely correct.
        // We pass the credentials as form data, which is more secure for OAuth2.
        const formData = new URLSearchParams();
        formData.append('username', email);
        formData.append('password', password);

        const response = await apiClient.post("/api/auth/login", formData, {
            // Override Content-Type for OAuth2 password grant flow
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded'
            }
        });

        // --- Handle Successful Login ---
        const data = response.data;
        localStorage.setItem("accessToken", data.access_token);

        // The backend should return user info upon successful login.
        // Let's assume it returns 'email' and 'display_name' in the response.
        localStorage.setItem("userEmail", data.email || email);
        localStorage.setItem("displayName", data.display_name || email.split('@')[0]);

        // Reload the page to reflect the logged-in state.
        window.location.reload();

    } catch (error) {
        // --- Handle Failed Login ---
        const errorMessage = error.response?.data?.detail || "Invalid credentials or server error.";
        showToast(`Login failed: ${errorMessage}`, "error");
    }
}

// --- USER REGISTRATION ---
// Handles the user registration form submission.
async function register() {
    // --- Get Form Values ---
    const name = document.getElementById("registerName").value;
    const email = document.getElementById("registerEmail").value;
    const password = document.getElementById("registerPassword").value;
    const passwordConfirm = document.getElementById("registerPasswordConfirm").value;

    // --- Input Validation ---
    if (!name || !email || !password || !passwordConfirm) {
        return showToast("Please fill out all required fields.", "error");
    }
    if (password !== passwordConfirm) {
        return showToast("Passwords do not match.", "error");
    }

    try {
        // --- API Call ---
        const response = await apiClient.post("/api/auth/register", {
            name,
            email,
            password,
            password_confirm: passwordConfirm
        });

        // --- Handle Success ---
        showToast(response.data.message || "Registration successful! Please log in.", "success");
        document.getElementById("registerForm").reset();
        showLogin(); // Assumes showLogin() switches to the login form

    } catch (error) {
        const errorMessage = error.response?.data?.detail || "An unknown error occurred during registration.";
        showToast(`Registration failed: ${errorMessage}`, "error");
    }
}

// --- USER LOGOUT ---
// Logs the user out by clearing local storage and notifying the backend.
async function logout() {
    try {
        // First, try to notify the backend. This is the proper first step.
        // This allows the server to invalidate the refresh token if it's stored in the database.
        await apiClient.post("/api/auth/logout");

    } catch (error) {
        // Even if the server call fails (e.g., user is offline), we should still
        // log the user out on the client side. We can log the error for debugging.
        console.error("Logout request to server failed, but logging out locally anyway:", error);

    } finally {
        // This block runs whether the try or catch block executed.
        // This is the correct place to clear client-side data.
        localStorage.removeItem("accessToken");
        localStorage.removeItem("userEmail");
        localStorage.removeItem("displayName");

        // Reload the page to reset the application state to a logged-out view.
        window.location.reload();
    }
}

function showRegister() { document.getElementById("loginBox").style.display = "none"; document.getElementById("registerBox").style.display = "block"; document.getElementById("resetBox").style.display = "none"; }
function showReset() { document.getElementById("loginBox").style.display = "none"; document.getElementById("resetBox").style.display = "block"; document.getElementById("registerBox").style.display = "none"; }
async function resetPassword() {
    const email = document.getElementById("resetEmail").value;
    if (!email) return showToast("Please enter an email address.", "error");

    try {
        await apiClient.post("/api/auth/reset-password", { email });
        showToast("Reset instructions sent!", "success");
    } catch (error) {
        const errorMessage = error.response?.data?.detail || "Reset failed.";
        showToast(errorMessage, "error");
    }
}

function showLogin() { document.getElementById("registerBox").style.display = "none"; document.getElementById("loginBox").style.display = "block"; document.getElementById("resetBox").style.display = "none"; }

// --- UPLOAD AND TRANSCRIBE A FILE ---
// Handles the file input, uploads to the server, and triggers transcription.
async function uploadFile() {
    const fileInput = document.getElementById("fileInput");
    const uploadBtn = document.getElementById("uploadBtn");

    // --- Input Validation ---
    if (!fileInput.files.length) {
        return showToast("Please select a file to upload.", "error");
    }

    // --- Prepare Form Data and UI for Uploading ---
    const formData = new FormData();
    formData.append("file", fileInput.files[0]);

    uploadBtn.disabled = true;
    uploadBtn.textContent = "Uploading...";
    document.getElementById("spinner").style.display = "inline-block";

    try {
        // --- API Call ---
        // Use apiClient.post. We must override the default 'Content-Type' header
        // for file uploads using FormData.
        const response = await apiClient.post("/api/transcription/upload", formData, {
            headers: {
                "Content-Type": "multipart/form-data",
            },
        });

        // --- Handle Success ---
        // The parsed JSON response is in `response.data`.
        const result = response.data;
        showToast(`Upload successful: ${result.filename}`, "success");

        // Refresh the history list to show the new file.
        loadHistory();

    } catch (error) {
        // --- Handle Failure ---
        // Provide a specific error message from the backend if available.
        const errorMessage = error.response?.data?.detail || "Upload failed. Please try again.";
        showToast(`Error: ${errorMessage}`, "error");

    } finally {
        // --- Reset UI State ---
        // This block runs after the try or catch, ensuring the UI is always reset.
        uploadBtn.disabled = false;
        uploadBtn.textContent = "Upload & Transcribe";
        document.getElementById("spinner").style.display = "none";
        fileInput.value = ""; // Clear the file input.
    }
}

// --- LOAD TRANSCRIPT HISTORY ---
// Fetches the list of all user transcripts from the backend.
async function loadHistory() {
    try {
        // Use the new apiClient. It handles auth, refresh tokens, and base URLs automatically.
        // A non-successful status (like 404 or 500) will automatically be caught by the catch block.
        const response = await apiClient.get("/api/transcription/transcripts");

        // With axios, the parsed JSON data is in the `data` property of the response.
        // We assign this array of transcript objects to our global variable.
        allTranscripts = response.data;

        // After fetching the latest data, call the function to display it.
        filterTranscripts();

    } catch (error) {
        // Provide more informative error messages to the user.
        // It first tries to get a specific error detail from the server's response.
        const errorMessage = error.response?.data?.detail || "Failed to load transcript history.";
        showToast(errorMessage, "error");
    }
}

function filterTranscripts() {
    const query = document.getElementById("searchInput").value.toLowerCase(), tagQuery = document.getElementById("tagSearchInput").value.toLowerCase(), sortBy = document.getElementById("sortSelect").value, historyDiv = document.getElementById("transcriptHistory");
    historyDiv.innerHTML = "<h3>Transcript History</h3>";
    let filtered = allTranscripts.filter(item => {
        const name = (item.filename || "").toLowerCase(), tag = (item.tag || "").toLowerCase();
        return name.includes(query) && (!tagQuery || tag.includes(tagQuery));
    });
    if (sortBy === "oldest") {
        filtered.sort((a, b) => new Date(a.upload_timestamp) - new Date(b.upload_timestamp));
    } else {
        filtered.sort((a, b) => new Date(b.upload_timestamp) - new Date(a.upload_timestamp));
    }
    if (filtered.length === 0) { historyDiv.innerHTML += "<p>No matching transcripts found.</p>"; } else { filtered.forEach(item => renderTranscriptItem(item, historyDiv)); }
}

function renderTranscriptItem(item, container) {
    const filename = item.filename, tag = item.tag, div = document.createElement("div");
    div.className = "history-item"; div.id = `history-item-${filename.replace(/[^a-zA-Z0-9]/g, '-')}`;
    div.innerHTML = `<span>📄 ${filename}</span> <input type="text" class="tag-input" data-filename="${filename}" placeholder="Add tag..." value="${tag || ''}"> <button class="tag-btn" data-filename="${filename}">Tag</button> <button class="details-btn" data-filename="${filename}">View Details</button> <button class="delete-btn" data-filename="${filename}">Delete</button>`;
    container.appendChild(div);
}

// --- UPDATE A TRANSCRIPT'S TAG ---
// Sends a new tag to the backend to be saved for a specific transcript.
async function updateTag(filename, tag) {
    try {
        // Use apiClient.post(). It automatically stringifies the body, sets the correct headers,
        // and handles authentication and token refreshing.
        await apiClient.post(`/api/transcription/transcript/${filename}/tag`, { tag: tag });

        // On success, notify the user and refresh the transcript list to show the new tag.
        showToast("Tag saved!", "success");
        loadHistory();

    } catch (error) {
        // Provide a more specific error message by checking the server's response.
        const errorMessage = error.response?.data?.detail || "Failed to update tag.";
        showToast("Error: " + errorMessage, "error");
    }
}

async function askQuestion() {
    const questionInput = document.getElementById("questionInput");
    const question = questionInput.value.trim();
    if (!question) return showToast("Please enter a question.", "error");

    // --- UI Setup ---
    const answerText = document.getElementById("answerText");
    const sourcesBox = document.getElementById("sourcesBox");
    const spinner = document.getElementById("askSpinner");

    answerText.textContent = "";
    sourcesBox.innerHTML = "";
    spinner.style.display = "inline-block";

    try {
        // --- API Call using fetch (Correct for Browser Streaming) ---
        const response = await fetch("/api/qa/ask", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                // Manually add the Authorization header for this specific call.
                Authorization: `Bearer ${localStorage.getItem("accessToken")}`
            },
            body: JSON.stringify({ question: question })
        });

        // Check for server errors (e.g., 4xx or 5xx status codes).
        if (!response.ok) {
            // Try to get a detailed error message from the server response.
            const errorData = await response.json().catch(() => ({ detail: "An unknown server error occurred." }));
            throw new Error(errorData.detail);
        }

        // --- Handle the Stream ---
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) break; // Exit the loop when the stream is finished.

            const chunk = decoder.decode(value, { stream: true });
            // The backend sends events separated by double newlines.
            for (const line of chunk.split("\n\n")) {
                if (line.startsWith("data: ")) {
                    try {
                        const payload = JSON.parse(line.slice(5));
                        // Process the different event types from the stream.
                        if (payload.type === "token") {
                            answerText.textContent += payload.data;
                        } else if (payload.type === "sources") {
                            payload.data.forEach(source => {
                                const block = document.createElement("div");
                                block.className = "source-block";
                                block.innerHTML = `<strong>Source:</strong> ${source.source || "Unknown"}<div class='source-text'>${source.text}</div>`;
                                sourcesBox.appendChild(block);
                            });
                        }
                    } catch (e) {
                        console.error("Error parsing stream data line:", line, e);
                    }
                }
            }
        }
    } catch (err) {
        console.error(err); // extra logging
        showToast("Error asking question: " + err.message, "error");
    }
} finally {
    // --- UI Cleanup ---
    spinner.style.display = "none";
    questionInput.value = "";
}
}

// --- DELETE & MODAL LOGIC ---
function showDeleteConfirm(filename) { pendingDeleteFilename = filename; document.getElementById('confirmDeleteModal').style.display = 'block'; }
function closeDeleteModal() { document.getElementById('confirmDeleteModal').style.display = 'none'; pendingDeleteFilename = null; }
async function confirmDelete() { if (pendingDeleteFilename) await deleteTranscript(pendingDeleteFilename); closeDeleteModal(); }

// --- DELETE A TRANSCRIPT ---
// Sends a request to the backend to delete a transcript and its associated files.
async function deleteTranscript(filename) {
    // A simple confirmation dialog is good practice for destructive actions.
    if (!confirm(`Are you sure you want to permanently delete "${filename}"?`)) {
        return; // Stop if the user clicks "Cancel".
    }

    try {
        // Use apiClient.delete(). It's a clean, declarative way to make a DELETE request.
        // Auth and token refreshing are handled automatically.
        await apiClient.delete(`/api/transcription/delete/${filename}`);

        // On success, notify the user and update the UI.
        showToast(`"${filename}" has been deleted.`, "success");
        loadHistory();
        closeTranscriptDetail();

    } catch (error) {
        // Provide more useful error feedback to the user.
        const errorMessage = error.response?.data?.detail || "Could not delete the transcript.";
        showToast("Error: " + errorMessage, "error");
    }
}

// --- TRANSCRIPT DETAIL LOGIC ---
// Fetches all data for a single transcript and displays it in the detail panel.
async function loadTranscriptForDetailView(filename) {
    // --- UI Setup (Keep this part as is) ---
    document.querySelectorAll('.history-item.active').forEach(el => el.classList.remove('active'));
    const itemDiv = document.getElementById(`history-item-${filename.replace(/[^a-zA-Z0-9]/g, '-')}`);
    if (itemDiv) itemDiv.classList.add("active");

    closeTranscriptDetail();
    editMode = false;

    const panel = document.getElementById("transcriptDetailPanel");
    const previewBox = document.getElementById("transcriptPreviewBox");
    const noteTextarea = document.getElementById("noteInput");
    const audioPlayer = document.getElementById("audioPlayer");

    panel.style.display = "block";
    document.getElementById("transcriptDetailFilename").innerText = filename;
    previewBox.innerHTML = "<em>Loading details...</em>";
    noteTextarea.value = "";
    noteTextarea.dataset.filename = filename;
    audioPlayer.style.display = 'none';
    document.getElementById("lastSavedTime").innerText = "";
    // --- End of UI Setup ---

    try {
        // Use Promise.all with apiClient to fetch all data in parallel.
        // The paths are now corrected to match the backend router prefixes.
        const [transcriptResponse, noteResponse, quizResponse] = await Promise.all([
            apiClient.get(`/api/transcription/transcript/${filename}`),
            apiClient.get(`/api/transcription/transcript/${filename}/note`),
            apiClient.get(`/api/transcription/quiz/${filename}`) // Also fetch the quiz data
        ]);

        // --- Process Transcript Data ---
        const transcriptData = transcriptResponse.data;
        previewBox.innerHTML = ""; // Clear the "Loading..." message

        if (transcriptData.segments && transcriptData.segments.length) {
            transcriptData.segments.forEach(seg => {
                const div = document.createElement("div");
                div.className = "transcript-segment";
                div.textContent = seg.text;
                div.dataset.start = seg.start;
                div.dataset.end = seg.end;
                div.onclick = () => playSegmentFrom(seg.start);
                previewBox.appendChild(div);
            });
        } else {
            // Fallback for transcripts without segments
            previewBox.innerText = transcriptData.transcript || "[Empty Transcript]";
        }

        // --- Process Audio ---
        // The audio URL is now directly from the database record, not a local file.
        // We'll get it from the `allTranscripts` array we loaded earlier.
        const transcriptRecord = allTranscripts.find(t => t.filename === filename);
        if (transcriptRecord && transcriptRecord.audio_url) {
            audioPlayer.src = transcriptRecord.audio_url;
            audioPlayer.style.display = 'block';
        }

        // --- Process Note Data ---
        noteTextarea.value = noteResponse.data.note || "";

        // --- Process and Display Quiz Data ---
        const quizData = quizResponse.data.quiz || [];
        displayQuizForTranscript(quizData, filename); // A new helper function to display the quiz

    } catch (error) {
        const errorMessage = error.response?.data?.detail || "Could not load transcript details.";
        showToast("Error: " + errorMessage, "error");
        previewBox.innerHTML = `<p style="color:red;">${errorMessage}</p>`;
    }
}

function closeTranscriptDetail() {
    document.getElementById("transcriptDetailPanel").style.display = "none";
    document.getElementById("summaryContainer").style.display = "none";
    document.getElementById("quizList").style.display = "none";
    const audioPlayer = document.getElementById("audioPlayer");
    if (audioPlayer) { audioPlayer.pause(); audioPlayer.src = ''; }
    stopSegmentHighlighter();
}
function playSegmentFrom(startTime) { const player = document.getElementById("audioPlayer"); player.currentTime = startTime; player.play(); }
function startSegmentHighlighter() { if (audioHighlightInterval) clearInterval(audioHighlightInterval); audioHighlightInterval = setInterval(highlightActiveSegment, 300); }
function stopSegmentHighlighter() { if (audioHighlightInterval) clearInterval(audioHighlightInterval); audioHighlightInterval = null; document.querySelectorAll('.transcript-segment.active').forEach(el => el.classList.remove('active')); }
function highlightActiveSegment() {
    const player = document.getElementById("audioPlayer"), currentTime = player.currentTime, segments = document.querySelectorAll('#transcriptPreviewBox .transcript-segment');
    let activeSegment = null;
    segments.forEach(seg => { const start = parseFloat(seg.dataset.start), end = parseFloat(seg.dataset.end); seg.classList.remove('active'); if (currentTime >= start && currentTime <= end) activeSegment = seg; });
    if (activeSegment) activeSegment.classList.add('active');
}

// --- TOGGLE SEGMENT EDITING MODE ---
// Switches the transcript view between display mode and an editable textarea mode.
function toggleEditSegments(button) {
    editMode = !editMode;
    const previewBox = document.getElementById("transcriptPreviewBox");
    const segments = previewBox.querySelectorAll('.transcript-segment, .segment-editor-wrapper');

    if (editMode) {
        button.textContent = "Cancel Edits";
        segments.forEach(seg => {
            // Get the current text, whether it's from a div or a textarea
            const text = seg.tagName === 'TEXTAREA' ? seg.value : seg.textContent;

            const wrapper = document.createElement('div');
            wrapper.className = 'segment-editor-wrapper';

            const textarea = document.createElement('textarea');
            textarea.className = 'segment-editor';
            textarea.value = text;
            textarea.rows = 3; // Or adjust as needed

            wrapper.appendChild(textarea);
            seg.replaceWith(wrapper);
        });
    } else {
        // If canceling, simply reload the transcript to discard changes.
        button.textContent = "Edit Segments";
        const filename = document.getElementById("noteInput").dataset.filename;
        if (filename) {
            loadTranscriptForDetailView(filename);
        }
    }
}


// --- SAVE EDITED SEGMENTS ---
// Saves the modified transcript segments back to the server.
async function saveEditedSegments() {
    const filename = document.getElementById("noteInput").dataset.filename;
    const textareas = document.querySelectorAll('#transcriptPreviewBox .segment-editor');

    try {
        // Step 1: Fetch the original transcript data to get timestamps and other metadata.
        const originalResponse = await apiClient.get(`/api/transcription/transcript/${filename}`);
        const originalSegments = originalResponse.data.segments || [];

        // Safety check: ensure the number of segments hasn't changed.
        if (textareas.length !== originalSegments.length) {
            showToast("Segment mismatch error. Please cancel and try again.", "error");
            return;
        }

        // Step 2: Create the new segments payload by combining old metadata with new text.
        const updatedSegments = originalSegments.map((seg, index) => {
            return {
                start: seg.start,
                end: seg.end,
                text: textareas[index].value // Use the new text from the textarea
            };
        });

        // Step 3: Send the updated data to the backend.
        await apiClient.post(`/api/transcription/transcript/${filename}/segments`, {
            segments: updatedSegments
        });

        // Step 4: On success, notify user and exit edit mode by reloading the view.
        showToast("Segments saved successfully!", "success");
        editMode = false;
        document.getElementById("editSegmentsBtn").textContent = "Edit Segments";
        loadTranscriptForDetailView(filename);

    } catch (error) {
        const errorMessage = error.response?.data?.detail || "Failed to save segments.";
        showToast("Error: " + errorMessage, "error");
    }
}

// --- SAVE THE ASSOCIATED NOTE ---
// Sends the content of the note textarea to the server to be saved.
async function saveNote() {
    const textarea = document.getElementById("noteInput");
    const note = textarea.value;
    const filename = textarea.dataset.filename;

    if (!filename) {
        showToast("Cannot save note: no transcript selected.", "error");
        return;
    }

    try {
        // Use apiClient.post(). It handles the method, headers, and body stringification.
        await apiClient.post(`/api/transcription/transcript/${filename}/note`, {
            note: note // The payload is a simple object with the note content.
        });

        // On success, provide immediate feedback to the user.
        document.getElementById("lastSavedTime").innerText = `Note saved at ${new Date().toLocaleTimeString()}`;

        // Optional: you could add a subtle success indicator, like a quick flash of green border.
        textarea.classList.add('save-success');
        setTimeout(() => textarea.classList.remove('save-success'), 1000);

    } catch (error) {
        // Provide specific error feedback.
        const errorMessage = error.response?.data?.detail || "Could not save the note.";
        showToast("Error: " + errorMessage, "error");

        // Throwing the error here might be useful if other functions need to know about the failure.
        throw error;
    }
}

async function saveAllEdits() {
    try {
        await Promise.all([saveEditedSegments(), saveNote()]);
        showToast("All changes saved!", "success");
        await loadTranscriptForDetailView(document.getElementById("noteInput").dataset.filename);
    } catch (err) { showToast("An error occurred during save.", "error"); }
}

function toggleSummary() { showToast("Toggle Summary not implemented yet.", "info"); }
function generateFullQuiz() { showToast("Generate Full Quiz not implemented yet.", "info"); }
function toggleQuizPanel() { showToast("Toggle Quiz Panel not implemented yet.", "info"); }
async function loadSavedQuiz() { /* Stub */ }
async function updateQuizQuestion() { /* Stub */ }
async function deleteQuizQuestion() { /* Stub */ }
async function exportTranscriptAsPDF() { showToast("Export to PDF not implemented yet.", "info"); }

// --- ONLOAD & EVENT LISTENERS ---
// --- ONLOAD & EVENT LISTENERS ---
window.onload = async () => {
    // A quick check: if there's no token at all, don't even try to call the server.
    if (!localStorage.getItem("accessToken")) {
        document.getElementById("appUI").style.display = "none";
        showLogin();
        return;
    }

    try {
        // The real test: can we fetch user data? apiClient will handle any needed token refresh.
        const response = await apiClient.get('/api/auth/me');
        const user = response.data; // The user object from the backend

        // If the above call succeeds, we are logged in.
        document.getElementById("appUI").style.display = "block";
        document.getElementById("loginBox").style.display = "none";

        // Use fresh data from the server to set local storage and UI elements.
        localStorage.setItem("displayName", user.name || user.email.split('@')[0]);
        localStorage.setItem("userEmail", user.email);
        document.getElementById("welcomeHeader").innerText = `Welcome, ${localStorage.getItem("displayName")}`;

        // Check role directly from the server response, which is more secure.
        if (user.role === "owner") {
            document.getElementById("analyticsToggle").style.display = "inline-block";
            document.getElementById("exportLogBtn").style.display = "inline-block";
        }

        loadHistory();

    } catch (error) {
        // If apiClient.get('/api/auth/me') fails, the token is invalid or expired.
        console.error("Session check failed, showing login:", error);
        document.getElementById("appUI").style.display = "none";
        showLogin();
    }

    // This part stays the same
    if (localStorage.getItem("prefDark") === "true") document.body.classList.add("dark");

    // ... all the event listeners should be attached here, at the end of the onload function ...
}

// Attach all event listeners
document.getElementById('logout').addEventListener('click', logout);
document.getElementById('profileToggle').addEventListener('click', toggleProfile);
document.getElementById('darkToggle').addEventListener('click', toggleDarkMode);
document.getElementById('analyticsToggle').addEventListener('click', toggleAnalytics);
document.getElementById('exportLogBtn').addEventListener('click', () => window.open('/api/admin/log/export', '_blank'));
document.getElementById('uploadBtn').addEventListener('click', uploadFile);
document.getElementById('searchInput').addEventListener('keyup', filterTranscripts);
document.getElementById('tagSearchInput').addEventListener('keyup', filterTranscripts);
document.getElementById('sortSelect').addEventListener('change', filterTranscripts);
document.getElementById('askQuestionBtn').addEventListener('click', askQuestion);
document.getElementById('loginBtn').addEventListener('click', login);
document.getElementById('registerBtn').addEventListener('click', register);
document.getElementById('resetPasswordBtn').addEventListener('click', resetPassword);
document.getElementById('showRegisterLink').addEventListener('click', showRegister);
document.getElementById('showResetLink').addEventListener('click', showReset);
document.getElementById('backToLoginFromRegister').addEventListener('click', showLogin);
document.getElementById('backToLoginFromReset').addEventListener('click', showLogin);
document.getElementById('closeTranscriptDetailBtn').addEventListener('click', closeTranscriptDetail);
document.getElementById('toggleEditSegmentsBtn').addEventListener('click', e => toggleEditSegments(e.target));
document.getElementById('toggleSummaryBtn').addEventListener('click', toggleSummary);
document.getElementById('generateFullQuizBtn').addEventListener('click', generateFullQuiz);
document.getElementById('toggleQuizPanelBtn').addEventListener('click', toggleQuizPanel);
document.getElementById('exportTranscriptAsPDFBtn').addEventListener('click', exportTranscriptAsPDF);
document.getElementById('saveAllEditsBtn').addEventListener('click', saveAllEdits);
document.getElementById('saveNoteBtn').addEventListener('click', saveNote);
document.getElementById('confirmDeleteBtn').addEventListener('click', confirmDelete);
document.getElementById('cancelDeleteBtn').addEventListener('click', closeDeleteModal);
document.getElementById('audioPlayer').addEventListener('play', startSegmentHighlighter);
document.getElementById('audioPlayer').addEventListener('pause', stopSegmentHighlighter);
document.getElementById('audioPlayer').addEventListener('ended', stopSegmentHighlighter);

document.getElementById('transcriptHistory').addEventListener('click', e => {
    if (e.target.matches('.details-btn')) loadTranscriptForDetailView(e.target.dataset.filename);
    if (e.target.matches('.delete-btn')) showDeleteConfirm(e.target.dataset.filename);
    if (e.target.matches('.tag-btn')) { const input = e.target.previousElementSibling; updateTag(input.dataset.filename, input.value); }
});
document.addEventListener('keydown', e => {
    if (e.key === "Escape") { closeDeleteModal(); closeTranscriptDetail(); }
    if (e.ctrlKey && e.key.toLowerCase() === 'd') { e.preventDefault(); toggleDarkMode(); }
});
    };

// Toggle password visibility for login

document.getElementById('showLoginPassword').addEventListener('change', e => {
    document.getElementById('loginPassword').type = e.target.checked ? "text" : "password";
});

// Toggle password visibility for register
document.getElementById('showRegisterPassword').addEventListener('change', e => {
    document.getElementById('registerPassword').type = e.target.checked ? "text" : "password";
    document.getElementById('registerPasswordConfirm').type = e.target.checked ? "text" : "password";
}); 
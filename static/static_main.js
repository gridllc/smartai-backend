// --- GLOBAL STATE ---
let allTranscripts = [];
let editMode = false;
let audioHighlightInterval = null;
let pendingDeleteFilename = null;

// --- AUTH & FETCH WRAPPER ---
async function fetchWithRefresh(url, options = {}, attempt = 0) {
    const token = localStorage.getItem("accessToken");
    options.headers = options.headers || {};
    if (token) options.headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(url, options);
    if (res.status === 401 && attempt === 0) {
        try {
            const refreshRes = await fetch("/auth/refresh-token", { method: "POST", credentials: "include" });
            if (!refreshRes.ok) throw new Error("Session expired.");
            const data = await refreshRes.json();
            localStorage.setItem("accessToken", data.access_token);
            return fetchWithRefresh(url, options, 1);
        } catch (e) {
            logout();
            throw e;
        }
    }
    return res;
}

async function tryRefreshToken() {
    try {
        const refreshRes = await fetch("/auth/refresh-token", { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" } });
        if (!refreshRes.ok) return false;
        const data = await refreshRes.json();
        localStorage.setItem("accessToken", data.access_token);
        if (data.user_email) localStorage.setItem("userEmail", data.user_email);
        if (data.display_name) localStorage.setItem("displayName", data.display_name);
        return true;
    } catch (e) {
        return false;
    }
}

// --- UI & UTILITY ---
function showToast(message, type = "info") { const bg = { success: "#4BB543", error: "#ff5c5c", info: "#3498db" }[type] || "#333"; Toastify({ text: message, duration: 3000, gravity: "top", position: "right", style: { background: bg } }).showToast(); }
function toggleDarkMode() { document.body.classList.toggle("dark"); localStorage.setItem("prefDark", document.body.classList.contains("dark")); }
function toggleProfile() { const profileBox = document.getElementById("profileBox"), overlay = document.getElementById("profileOverlay"), isVisible = profileBox.style.display === "block"; profileBox.style.display = isVisible ? "none" : "block"; if (overlay) overlay.style.display = isVisible ? "none" : "block"; }
function toggleAnalytics() { showToast("Analytics not implemented yet.", "info"); }

// --- AUTH & USER ---
function login() {
    const email = document.getElementById("loginEmail").value;
    const password = document.getElementById("loginPassword").value;

    if (!email || !password) {
        return showToast("Please enter email and password.", "error");
    }

    fetch("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email, password })
    })
        .then(res => {
            if (!res.ok) {
                // This will handle 401 Unauthorized, etc.
                return res.json().then(errorData => {
                    // Throw an error with the specific message from the backend
                    throw new Error(errorData.detail || "Invalid credentials or server error.");
                });
            }
            return res.json();
        })
        .then(data => {
            localStorage.setItem("accessToken", data.access_token);
            localStorage.setItem("userEmail", email);
            // Now 'display_name' will be correctly populated from the improved backend
            localStorage.setItem("displayName", data.display_name || email.split('@')[0]);
            window.location.reload();
        })
        .catch(error => {
            // This single catch block now handles network errors and our thrown errors
            showToast(`Login failed: ${error.message}`, "error");
        });
}

function register() {
    const name = document.getElementById("registerName").value,
        email = document.getElementById("registerEmail").value,
        password = document.getElementById("registerPassword").value,
        passwordConfirm = document.getElementById("registerPasswordConfirm").value;

    if (!name || !email || !password || !passwordConfirm)
        return showToast("Please fill out all required fields.", "error");

    if (password !== passwordConfirm)
        return showToast("Passwords do not match.", "error");

    fetch("/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            name: name,
            email: email,
            password: password,
            password_confirm: passwordConfirm
        })
    })
        .then(res => {
            // This is a robust way to handle JSON responses for both success and error cases.
            return res.json().then(data => {
                if (!res.ok) {
                    // If the response is not OK (e.g., status 400), we throw an error.
                    // The error message will be the 'detail' field from the backend's JSON response.
                    throw new Error(data.detail || 'An unknown error occurred during registration.');
                }
                // If the response is OK, we return the data for the next .then() block.
                return data;
            });
        })
        .then(data => {
            // This block only executes for a successful registration.
            showToast(data.message || "Registration successful! Please log in.", "success");
            // Directly show the login form for a better user experience.
            showLogin();
        })
        .catch(error => {
            // This block catches both network errors and the specific error we threw above.
            // It will now display the helpful error message from the backend.
            showToast(`Registration failed: ${error.message}`, "error");
        });
}

function logout() { localStorage.clear(); fetch("/auth/logout", { method: "POST", credentials: "include" }).finally(() => window.location.reload()); }
function showRegister() { document.getElementById("loginBox").style.display = "none"; document.getElementById("registerBox").style.display = "block"; document.getElementById("resetBox").style.display = "none"; }
function showReset() { document.getElementById("loginBox").style.display = "none"; document.getElementById("resetBox").style.display = "block"; document.getElementById("registerBox").style.display = "none"; }
function resetPassword() {
    const email = document.getElementById("resetEmail").value;
    fetch("/reset-password", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email }) })
        .then(res => res.ok ? res.json() : Promise.reject(res.json()))
        .then(() => showToast("Reset email sent!", "success"))
        .catch(() => showToast("Reset failed.", "error"));
}
function showLogin() { document.getElementById("registerBox").style.display = "none"; document.getElementById("loginBox").style.display = "block"; document.getElementById("resetBox").style.display = "none"; }

// --- CORE APP: UPLOAD, HISTORY, ASK ---
async function uploadFile() {
    const fileInput = document.getElementById("fileInput"), uploadBtn = document.getElementById("uploadBtn");
    if (!fileInput.files.length) return showToast("Please select a file to upload.", "error");
    const formData = new FormData(); formData.append("file", fileInput.files[0]);
    uploadBtn.disabled = true; uploadBtn.textContent = "Uploading..."; document.getElementById("spinner").style.display = "inline-block";
    try {
        const res = await fetchWithRefresh("/api/upload", { method: "POST", body: formData });
        if (!res.ok) throw new Error((await res.json()).detail || "Upload failed");
        const result = await res.json();
        showToast("Upload successful: " + result.filename, "success");
        loadHistory();
    } catch (err) {
        showToast("Error: " + err.message, "error");
    } finally {
        uploadBtn.disabled = false; uploadBtn.textContent = "Upload & Transcribe"; document.getElementById("spinner").style.display = "none"; fileInput.value = "";
    }
}
async function loadHistory() {
    try {
        const res = await fetchWithRefresh("/api/transcripts");
        if (!res.ok) throw new Error("Failed to load history");

        // FIX: The backend returns an array directly, not an object with a .files property.
        allTranscripts = await res.json();

        filterTranscripts();
    } catch (err) { showToast(err.message, "error"); }
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
async function updateTag(filename, tag) {
    try {
        const res = await fetchWithRefresh(`/api/transcript/${filename}/tag`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tag }) });
        if (!res.ok) throw new Error("Failed to update tag");
        showToast("Tag saved!", "success"); loadHistory();
    } catch (err) { showToast("Error updating tag: " + err.message, "error"); }
}
async function askQuestion() {
    const questionInput = document.getElementById("questionInput"), question = questionInput.value.trim();
    if (!question) return showToast("Please enter a question.", "error");
    const answerText = document.getElementById("answerText"), sourcesBox = document.getElementById("sourcesBox"), spinner = document.getElementById("answerSpinner");
    answerText.textContent = ""; sourcesBox.innerHTML = ""; spinner.style.display = "inline-block";
    try {
        const response = await fetchWithRefresh("/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }) });
        if (!response.ok || !response.body) throw new Error((await response.json()).detail || "Server error");
        const reader = response.body.getReader(), decoder = new TextDecoder();
        while (true) {
            const { done, value } = await reader.read(); if (done) break;
            for (const line of decoder.decode(value, { stream: true }).split("\n\n")) {
                if (!line.startsWith("data:")) continue;
                try {
                    const payload = JSON.parse(line.slice(5));
                    if (payload.type === "token") answerText.textContent += payload.data;
                    else if (payload.type === "sources") { payload.data.forEach(source => { const block = document.createElement("div"); block.className = "source-block"; block.innerHTML = `<strong>Source:</strong> ${source.source || "Unknown"}<div class='source-text'>${source.text}</div>`; sourcesBox.appendChild(block); }); }
                } catch (e) { console.error("Stream parse error:", e); }
            }
        }
    } catch (err) { showToast("Error asking question: " + err.message, "error"); } finally { spinner.style.display = "none"; questionInput.value = ""; }
}

// --- DELETE & MODAL LOGIC ---
function showDeleteConfirm(filename) { pendingDeleteFilename = filename; document.getElementById('confirmDeleteModal').style.display = 'block'; }
function closeDeleteModal() { document.getElementById('confirmDeleteModal').style.display = 'none'; pendingDeleteFilename = null; }
async function confirmDelete() { if (pendingDeleteFilename) await deleteTranscript(pendingDeleteFilename); closeDeleteModal(); }
async function deleteTranscript(filename) {
    try {
        const res = await fetchWithRefresh(`/api/delete/${filename}`, { method: "DELETE" });
        if (!res.ok) throw new Error("Delete failed");
        showToast(`${filename} deleted.`, "info"); loadHistory(); closeTranscriptDetail();
    } catch (err) { showToast("Delete error: " + err.message, "error"); }
}

// --- TRANSCRIPT DETAIL LOGIC ---
async function loadTranscriptForDetailView(filename) {
    document.querySelectorAll('.history-item.active').forEach(el => el.classList.remove('active'));
    const itemDiv = document.getElementById(`history-item-${filename.replace(/[^a-zA-Z0-9]/g, '-')}`);
    if (itemDiv) itemDiv.classList.add("active");
    closeTranscriptDetail(); editMode = false;
    const panel = document.getElementById("transcriptDetailPanel"), previewBox = document.getElementById("transcriptPreviewBox"), noteTextarea = document.getElementById("noteInput"), audioPlayer = document.getElementById("audioPlayer");
    panel.style.display = "block"; document.getElementById("transcriptDetailFilename").innerText = filename;
    previewBox.innerHTML = "<em>Loading...</em>"; noteTextarea.value = ""; noteTextarea.dataset.filename = filename; audioPlayer.style.display = 'none'; document.getElementById("lastSavedTime").innerText = "";
    try {
        const [transcriptRes, noteRes, audioRes] = await Promise.all([fetchWithRefresh(`/api/transcript/${filename}`), fetchWithRefresh(`/api/transcript/${filename}/note`), fetchWithRefresh(`/audio/${filename}`)]);
        if (!transcriptRes.ok) throw new Error("Transcript load failed");
        const transcriptData = await transcriptRes.json();
        previewBox.innerHTML = "";
        if (transcriptData.segments && transcriptData.segments.length) {
            transcriptData.segments.forEach(seg => { const div = document.createElement("div"); div.className = "transcript-segment"; div.textContent = seg.text; div.dataset.start = seg.start; div.dataset.end = seg.end; div.onclick = () => playSegmentFrom(seg.start); previewBox.appendChild(div); });
        } else { previewBox.innerText = transcriptData.transcript || "[Empty]"; }
        if (audioRes.ok) { const audioBlob = await audioRes.blob(); audioPlayer.src = URL.createObjectURL(audioBlob); audioPlayer.style.display = 'block'; }
        const noteData = noteRes.ok ? await noteRes.json() : { note: "" }; noteTextarea.value = noteData.note || "";
    } catch (err) { showToast("Error loading details: " + err.message, "error"); previewBox.innerHTML = `<p style="color:red;">Failed to load details.</p>`; }
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
function toggleEditSegments(button) {
    editMode = !editMode;
    const previewBox = document.getElementById("transcriptPreviewBox");
    const segments = previewBox.querySelectorAll('.transcript-segment, .segment-editor-wrapper');
    if (editMode) {
        button.textContent = "Cancel Edits";
        segments.forEach(seg => {
            const text = seg.tagName === 'TEXTAREA' ? seg.value : seg.textContent;
            const wrapper = document.createElement('div'); wrapper.className = 'segment-editor-wrapper';
            const textarea = document.createElement('textarea'); textarea.className = 'segment-editor'; textarea.value = text; textarea.rows = 3;
            wrapper.appendChild(textarea); seg.replaceWith(wrapper);
        });
    } else { button.textContent = "Edit Segments"; loadTranscriptForDetailView(document.getElementById("noteInput").dataset.filename); }
}
async function saveEditedSegments() {
    const filename = document.getElementById("noteInput").dataset.filename;
    const textareas = document.querySelectorAll('#transcriptPreviewBox .segment-editor');
    // We need to re-fetch original segments to get timestamps as they are lost in edit mode
    const transcriptRes = await fetchWithRefresh(`/api/transcript/${filename}`);
    const originalData = await transcriptRes.json();
    const originalSegments = originalData.segments || [];

    if (textareas.length !== originalSegments.length) {
        showToast("Segment mismatch error. Cannot save.", "error");
        return;
    }

    const updatedSegments = Array.from(textareas).map((textarea, index) => ({
        text: textarea.value,
        start: originalSegments[index].start,
        end: originalSegments[index].end
    }));

    try {
        const res = await fetchWithRefresh(`/api/transcript/${filename}/segments`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ segments: updatedSegments }) });
        if (!res.ok) throw new Error("Failed to save segments");
        document.getElementById("lastSavedTime").innerText = `Last saved: ${new Date().toLocaleTimeString()}`;
    } catch (err) { showToast("Error saving segments: " + err.message, "error"); throw err; }
}
async function saveNote() {
    const textarea = document.getElementById("noteInput"), note = textarea.value, filename = textarea.dataset.filename;
    if (!filename) return;
    try {
        const res = await fetchWithRefresh(`/api/transcript/${filename}/note`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ note }) });
        if (!res.ok) throw new Error("Note save failed");
        document.getElementById("lastSavedTime").innerText = `Last saved: ${new Date().toLocaleTimeString()}`;
    } catch (err) { showToast("Note save error: " + err.message, "error"); throw err; }
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
window.onload = async () => {
    const isLoggedIn = await tryRefreshToken();
    if (isLoggedIn) {
        document.getElementById("appUI").style.display = "block"; document.getElementById("loginBox").style.display = "none";
        document.getElementById("welcomeHeader").innerText = `Welcome, ${localStorage.getItem("displayName") || "User"}`;
        const currentUser = localStorage.getItem("userEmail");
        if (currentUser === "patrick@gridllc.net") { document.getElementById("analyticsToggle").style.display = "inline-block"; document.getElementById("exportLogBtn").style.display = "inline-block"; }
        loadHistory();
    } else {
        document.getElementById("appUI").style.display = "none"; showLogin();
    }
    if (localStorage.getItem("prefDark") === "true") document.body.classList.add("dark");

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
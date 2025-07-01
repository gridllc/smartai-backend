// --- FILE: static_main.js ---

// ... (keep the rest of the file the same)

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
// ... (rest of the file is correct)
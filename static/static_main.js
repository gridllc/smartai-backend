document.getElementById("uploadBtn").addEventListener("click", async () => {
    const fileInput = document.getElementById("fileInput");
    const uploadBtn = document.getElementById("uploadBtn");

    if (!fileInput.files.length) {
        Toastify({
            text: "Please select a file to upload.",
            duration: 3000,
            gravity: "bottom",
            position: "center",
            style: {
                background: "#ff5c5c"
            }
        }).showToast();
        return;
    }

    const formData = new FormData();
    formData.append("file", fileInput.files[0]);

    uploadBtn.disabled = true;
    uploadBtn.textContent = "Uploading...";

    const spinner = document.getElementById("spinner");
    spinner.style.display = "block";  // Show before fetch
    // ... do work ...
    spinner.style.display = "none";   // Hide in finally{}

    try {
        const res = await fetch("/api/upload", {
            method: "POST",
            body: formData,
            headers: {
                Authorization: "Bearer " + localStorage.getItem("accessToken")
            }
        });

        if (!res.ok) {
            const error = await res.json();
            throw new Error(error.detail || "Upload failed");
        }

        const result = await res.json();

        Toastify({
            text: "Upload successful: " + result.filename,
            duration: 4000,
            gravity: "bottom",
            position: "center",
            style: {
                background: "#4BB543"
            }
        }).showToast();

        // Optional: reload or update transcript list
        if (typeof loadTranscriptList === "function") {
            loadTranscriptList();
        }

    } catch (err) {
        Toastify({
            text: "Error: " + err.message,
            duration: 4000,
            gravity: "bottom",
            position: "center",
            style: {
                background: "#ff5c5c"
            }
        }).showToast();
    } finally {
        uploadBtn.disabled = false;
        uploadBtn.textContent = "Upload & Transcribe";
    }
});


async function tryRefreshToken() {
    console.log("Attempting to refresh token on page load...");
    try {
        const refreshRes = await fetch("/refresh-token", {
            method: "POST",
            credentials: "include",
            headers: {
                "Content-Type": "application/json"
            }
        });

        if (!refreshRes.ok) {
            console.log("No active session found via refresh token.");
            return false;
        }

        const data = await refreshRes.json();
        localStorage.setItem("accessToken", data.access_token);
        if (data.user_email) localStorage.setItem("userEmail", data.user_email);
        if (data.display_name) localStorage.setItem("displayName", data.display_name);

        console.log("Silent refresh successful. User is logged in.");
        return true;
    } catch (e) {
        console.error("Error during silent token refresh:", e);
        return false;
    }
}


async function loadHistory() {
    try {
        let res = await fetch("/api/transcripts", {
            headers: { "Authorization": "Bearer " + localStorage.getItem("accessToken") }
        });

        if (res.status === 401) {
            const refreshed = await tryAutoRefreshToken();
            if (refreshed) {
                res = await fetch("/api/transcripts", {
                    headers: { "Authorization": "Bearer " + localStorage.getItem("accessToken") }
                });
            } else {
                showToast("Session expired. Please log in again.", "error");
                logout();
                return;
            }
        }

        const data = await res.json();
        allTranscripts = data.files || [];
        filterTranscripts();
    } catch (err) {
        showToast("Error loading history: " + err.message, "error");
    }
}
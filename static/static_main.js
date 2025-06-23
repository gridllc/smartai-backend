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
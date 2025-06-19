
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>SmartAI Audio Transcriber</title>
  <link rel="stylesheet" href="/static/style.css" />
  <link rel="stylesheet" type="text/css" href="https://cdn.jsdelivr.net/npm/toastify-js/src/toastify.min.css">
  <script type="text/javascript" src="https://cdn.jsdelivr.net/npm/toastify-js"></script>
  <style>
    body.dark { background-color: #111; color: #eee; }
    .dark input, .dark button { background-color: #222; color: #fff; border-color: #555; }
    .spinner { display: inline-block; width: 20px; height: 20px; border: 3px solid #f3f3f3; border-top: 3px solid #555; border-radius: 50%; animation: spin 1s linear infinite; margin-left: 10px; }
    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    #answerText { white-space: pre-wrap; font-size: 1rem; line-height: 1.5; }
    .source-block { margin-top: 10px; padding: 10px; border: 1px solid #aaa; border-radius: 6px; background: #f9f9f9; font-size: 0.9em; }
    .source-text { margin-top: 5px; color: #333; cursor: pointer; }
    .history-item { margin: 10px 0; padding: 5px; border-bottom: 1px solid #ccc; }
    .history-item button { margin-left: 10px; }
    #logout, #darkToggle { float: right; margin-left: 10px; }
    #adminPanel { margin-top: 20px; border: 1px solid #aaa; padding: 10px; display: none; }
    #activityLog { max-height: 300px; overflow-y: auto; border: 1px solid #ccc; padding: 10px; margin-top: 10px; }
  </style>
</head>
<body>
  <!-- Login UI -->
  <div id="loginBox">
    <h2>Login</h2>
    <input type="email" id="loginEmail" placeholder="Email" />
    <input type="password" id="loginPassword" placeholder="Password" />
    <button onclick="login()">Login</button>
    <p>Need an account? <a href="#" onclick="showRegister()">Register here</a></p>
    <p><a href="#" onclick="showReset()">Forgot Password?</a></p>
  </div>

  <!-- Password Reset UI -->
  <div id="resetBox" style="display:none">
    <h2>Reset Password</h2>
    <input type="email" id="resetEmail" placeholder="Email" />
    <input type="password" id="newPassword" placeholder="New Password" />
    <input type="text" id="resetCode" placeholder="Invite Code" />
    <button onclick="resetPassword()">Reset Password</button>
    <p><a href="#" onclick="showLogin()">Back to Login</a></p>
  </div>

  <!-- Registration UI -->
  <div id="registerBox" style="display:none">
    <h2>Register</h2>
    <input type="text" id="registerName" placeholder="Full Name" />
    <input type="email" id="registerEmail" placeholder="Email" />
    <input type="password" id="registerPassword" placeholder="Password" />
    <input type="text" id="registerCode" placeholder="Invite Code" />
    <button onclick="register()">Register</button>
    <p>Already have an account? <a href="#" onclick="showLogin()">Go to login</a></p>
  </div>

  <!-- Main App UI -->
  <div id="appUI" style="display: none">
    <button id="logout" onclick="logout()">Logout</button>
    <button id="darkToggle" onclick="toggleDarkMode()">🌙 Toggle Dark</button>
    <h1 id="welcomeHeader">SmartAI Audio Transcriber</h1>
    <input type="file" id="fileInput" />
    <button onclick="uploadFile()">Upload & Transcribe</button>
    <button onclick="downloadAll()">Download All</button>
    <div>
      <input type="text" id="searchInput" placeholder="Search transcripts..." oninput="filterTranscripts()" />
      <select id="sortSelect" onchange="filterTranscripts()">
        <option value="newest">Newest First</option>
        <option value="oldest">Oldest First</option>
      </select>
    </div>
    <div id="transcriptHistory"></div>
    <hr>
    <h2>Ask a Question</h2>
    <input type="text" id="questionInput" placeholder="Ask a question..." />
    <button onclick="askQuestion()">Ask</button>
    <div id="spinner" class="spinner" style="display: none;"></div>
    <div id="answerBox">
      <div id="answerText"></div>
      <div id="sourcesBox"></div>
    </div>
    <div id="adminPanel">
      <h3>Admin Panel</h3>
      <p>This section is only visible to admin users.</p>
      <button onclick="loadActivityLog()">Refresh Activity Log</button>
      <div id="activityLog"></div>
    </div>
  </div>

  <script>
    let currentUser = null;
    let allTranscripts = [];

    function showToast(message, type = "info") {
      let bg = { success: "#4CAF50", error: "#f44336", info: "#2196F3" }[type] || "#333";
      Toastify({ text: message, duration: 3000, gravity: "top", position: "right", backgroundColor: bg }).showToast();
    }

    function logout() {
      localStorage.removeItem("token");
      document.getElementById("loginBox").style.display = "block";
      document.getElementById("appUI").style.display = "none";
      document.getElementById("registerBox").style.display = "none";
      document.getElementById("resetBox").style.display = "none";
      document.getElementById("adminPanel").style.display = "none";
      showToast("Logged out", "info");
    }

    function toggleDarkMode() {
      document.body.classList.toggle("dark");
    }

    function showRegister() {
      document.getElementById("loginBox").style.display = "none";
      document.getElementById("registerBox").style.display = "block";
      document.getElementById("resetBox").style.display = "none";
    }

    function showLogin() {
      document.getElementById("registerBox").style.display = "none";
      document.getElementById("loginBox").style.display = "block";
      document.getElementById("resetBox").style.display = "none";
    }

    function showReset() {
      document.getElementById("loginBox").style.display = "none";
      document.getElementById("resetBox").style.display = "block";
    }

    async function resetPassword() {
      const email = document.getElementById("resetEmail").value;
      const password = document.getElementById("newPassword").value;
      const code = document.getElementById("resetCode").value;

      try {
        const res = await fetch("/reset-password", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password, code })
        });

        if (!res.ok) throw new Error("Reset failed");
        
        showToast("Password updated!", "success");
        showLogin();
      } catch (err) {
        showToast("Reset error: " + err.message, "error");
      }
    }

    async function downloadAll() {
      window.location.href = "/api/download/all";
    }

    async function loadActivityLog() {
      const res = await fetch("/api/activity-log", {
        headers: { "Authorization": "Bearer " + localStorage.getItem("token") }
      });
      const data = await res.json();
      const logDiv = document.getElementById("activityLog");
      logDiv.innerHTML = "<h4>Recent Activity</h4><ul>" +
        data.log.map(e => `<li>${e[1]} - ${e[2] || "(no file)"} by ${e[0]} @ ${e[3]}</li>`).join("") +
        "</ul>";
    }

    async function uploadFile() {
      const fileInput = document.getElementById("fileInput");
      const file = fileInput.files[0];

      if (!file) {
        showToast("Please select a file to upload.", "error");
        return;
      }

      const formData = new FormData();
      formData.append("file", file);

      const spinner = document.getElementById("spinner");
      spinner.style.display = "inline-block";

      try {
        const res = await fetch("/upload-and-transcribe", {
          method: "POST",
          headers: {
            "Authorization": "Bearer " + localStorage.getItem("token")
          },
          body: formData
        });

        if (!res.ok) {
          const error = await res.json();
          throw new Error(error.detail || "Upload failed");
        }

        showToast("Upload and transcription successful!", "success");
        loadHistory();
      } catch (err) {
        console.error("Upload error:", err);
        showToast("Upload error: " + err.message, "error");
      } finally {
        spinner.style.display = "none";
      }
    }

    async function askQuestion() {
      const questionInput = document.getElementById("questionInput");
      const question = questionInput.value.trim();
      
      if (!question) {
        showToast("Please enter a question.", "error");
        return;
      }

      const spinner = document.getElementById("spinner");
      spinner.style.display = "inline-block";

      try {
        const res = await fetch("/ask", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + localStorage.getItem("token")
          },
          body: JSON.stringify({ question })
        });

        if (!res.ok) {
          const error = await res.json();
          throw new Error(error.detail || "Question failed");
        }

        const data = await res.json();
        
        document.getElementById("answerText").textContent = data.answer;
        
        const sourcesBox = document.getElementById("sourcesBox");
        sourcesBox.innerHTML = "";
        
        if (data.sources && data.sources.length > 0) {
          data.sources.forEach(source => {
            const sourceDiv = document.createElement("div");
            sourceDiv.className = "source-block";
            sourceDiv.innerHTML = `
              <strong>Source:</strong> ${source.source || "Unknown"}
              <div class="source-text">${source.text}</div>
            `;
            sourcesBox.appendChild(sourceDiv);
          });
        }

        questionInput.value = "";
      } catch (err) {
        console.error("Question error:", err);
        showToast("Question error: " + err.message, "error");
      } finally {
        spinner.style.display = "none";
      }
    }

    function login() {
      const email = document.getElementById("loginEmail").value;
      const password = document.getElementById("loginPassword").value;

      fetch("/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password })
      }).then(res => {
        if (!res.ok) throw new Error("Login failed");
        return res.json();
      }).then(data => {
        localStorage.setItem("token", data.access_token);
        currentUser = email;
        document.getElementById("loginBox").style.display = "none";
        document.getElementById("appUI").style.display = "block";
        document.getElementById("welcomeHeader").innerText = `Welcome, ${email}`;
        if (email === "patrick@gridllc.net") {
          document.getElementById("adminPanel").style.display = "block";
        }
        loadHistory();
        showToast("Login successful", "success");
      }).catch(err => {
        showToast("Login error: " + err.message, "error");
      });
    }

    function register() {
      const full_name = document.getElementById("registerName").value;
      const email = document.getElementById("registerEmail").value;
      const password = document.getElementById("registerPassword").value;
      const invite_code = document.getElementById("registerCode").value;

      fetch("/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password })
      }).then(res => {
        if (!res.ok) throw new Error("Registration failed");
        return res.json();
      }).then(() => {
        showToast("Account created! Please login.", "success");
        showLogin();
      }).catch(err => {
        showToast("Registration error: " + err.message, "error");
      });
    }

    function filterTranscripts() {
      const query = document.getElementById("searchInput").value.toLowerCase();
      const sortBy = document.getElementById("sortSelect").value;
      let filtered = allTranscripts.filter(name => name.toLowerCase().includes(query));
      if (sortBy === "newest") filtered.reverse();

      const historyDiv = document.getElementById("transcriptHistory");
      historyDiv.innerHTML = "<h3>Transcript History</h3>";
      filtered.forEach(renderTranscriptItem);
    }

    function renderTranscriptItem(filename) {
      const div = document.createElement("div");
      div.className = "history-item";

      const nameSpan = document.createElement("span");
      nameSpan.innerText = `📄 ${filename}`;

      const previewBtn = document.createElement("button");
      previewBtn.innerText = "Preview";
      const previewBox = document.createElement("div");
      previewBox.style.display = "none";
      previewBox.style.marginTop = "5px";
      previewBox.style.padding = "6px";
      previewBox.style.border = "1px solid #ccc";
      previewBox.style.borderRadius = "4px";
      previewBox.style.background = "#f9f9f9";
      previewBox.style.whiteSpace = "pre-wrap";

      previewBtn.onclick = async () => {
        if (previewBox.style.display === "none") {
          const res = await fetch(`/api/transcript/${filename}`, {
            headers: { "Authorization": "Bearer " + localStorage.getItem("token") }
          });
          const data = await res.json();
          previewBox.innerText = data.transcript || "[Empty]";
          previewBox.style.display = "block";
        } else {
          previewBox.style.display = "none";
        }
      };

      const downloadBtn = document.createElement("button");
      downloadBtn.innerText = "Download";
      downloadBtn.onclick = () => window.location.href = `/api/download/${filename}`;

      const deleteBtn = document.createElement("button");
      deleteBtn.innerText = "Delete";
      deleteBtn.onclick = async () => {
        if (confirm(`Delete ${filename}?`)) {
          await fetch(`/api/delete/${filename}`, {
            method: "DELETE",
            headers: { "Authorization": "Bearer " + localStorage.getItem("token") }
          });
          loadHistory();
          showToast(`${filename} deleted.`, "info");
        }
      };

      div.appendChild(nameSpan);
      div.appendChild(previewBtn);
      div.appendChild(downloadBtn);
      div.appendChild(deleteBtn);
      div.appendChild(previewBox);

      document.getElementById("transcriptHistory").appendChild(div);
    }

    async function loadHistory() {
      const res = await fetch("/api/history", {
        headers: { "Authorization": "Bearer " + localStorage.getItem("token") }
      });
      const data = await res.json();
      allTranscripts = data.files || [];
      filterTranscripts();
    }

    window.onload = () => {
      const token = localStorage.getItem("token");
      if (token) {
        currentUser = token;
        document.getElementById("loginBox").style.display = "none";
        document.getElementById("appUI").style.display = "block";
        document.getElementById("welcomeHeader").innerText = `Welcome, ${currentUser}`;
        if (currentUser === "patrick@gridllc.net") {
          document.getElementById("adminPanel").style.display = "block";
        }
        loadHistory();
      } else {
        document.getElementById("loginBox").style.display = "block";
        document.getElementById("registerBox").style.display = "none";
        document.getElementById("appUI").style.display = "none";
      }
    };
  </script>
</body>
</html>
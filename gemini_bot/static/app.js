// Регистрация Service Worker для PWA
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js", { scope: "/" })
      .then((reg) => console.log("PWA Service Worker registered:", reg.scope))
      .catch((err) => console.warn("PWA Service Worker registration failed:", err));
  });
}

// Управление состоянием приложения
const state = {
  currentTab: "chat",
  deferredPrompt: null,
  config: {
    style: "default",
    temperature: 0.7,
    rules: []
  },
  tasks: []
};

// Простой рендерер Markdown в HTML
function parseMarkdown(text) {
  if (!text) return "";
  let html = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // Блоки кода
  html = html.replace(/```([a-z]*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
  // Инлайн код
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  // Жирный шрифт
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  // Курсив
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  // Переносы строк
  html = html.replace(/\n/g, '<br>');

  return html;
}

// -------------------------------------------------------------
// 1. Навигация по вкладкам (Tabs)
// -------------------------------------------------------------
function setupTabs() {
  const navButtons = document.querySelectorAll(".nav-item");
  const tabPanes = document.querySelectorAll(".tab-pane");
  const inputBar = document.getElementById("chatInputBar");

  navButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetTab = btn.getAttribute("data-tab");
      state.currentTab = targetTab;

      navButtons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");

      tabPanes.forEach((pane) => {
        if (pane.id === `tab-${targetTab}`) {
          pane.classList.add("active");
        } else {
          pane.classList.remove("active");
        }
      });

      // Показываем строку ввода только на вкладке чата
      if (inputBar) {
        inputBar.style.display = targetTab === "chat" ? "flex" : "none";
      }

      if (targetTab === "config") loadConfig();
      if (targetTab === "tasks") loadTasks();
    });
  });
}

// -------------------------------------------------------------
// 2. Логика Чата (Chat)
// -------------------------------------------------------------
function setupChat() {
  const chatMessages = document.getElementById("chatMessages");
  const chatInput = document.getElementById("chatInput");
  const sendBtn = document.getElementById("sendBtn");

  const chatModelSelect = document.getElementById("chatModelSelect");

  async function loadModels() {
    try {
      const res = await fetch("/api/models");
      const data = await res.json();
      if (data.models && chatModelSelect) {
        chatModelSelect.innerHTML = "";
        data.models.forEach((m) => {
          const opt = document.createElement("option");
          opt.value = m.id;
          const icon = m.id === "auto-hermes" ? "✨" : (m.configured ? "🟢" : "🔑");
          opt.textContent = `${icon} ${m.name.replace(/^[^\s]+\s+/, '')}`;
          if (m.id === data.current_model) opt.selected = true;
          chatModelSelect.appendChild(opt);
        });
      }
    } catch (e) {
      console.warn("Failed to load models list:", e);
    }
  }
  loadModels();

  function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function appendMessage(role, text) {
    const bubble = document.createElement("div");
    bubble.className = `message-bubble ${role}`;
    bubble.innerHTML = parseMarkdown(text);
    chatMessages.appendChild(bubble);
    scrollToBottom();
  }

  function showTyping() {
    const indicator = document.createElement("div");
    indicator.className = "typing-indicator";
    indicator.id = "typingIndicator";
    indicator.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';
    chatMessages.appendChild(indicator);
    scrollToBottom();
  }

  function removeTyping() {
    const indicator = document.getElementById("typingIndicator");
    if (indicator) indicator.remove();
  }

  async function sendMessage() {
    const text = chatInput.value.trim();
    if (!text) return;
    const selectedModel = chatModelSelect ? chatModelSelect.value : "auto-hermes";

    appendMessage("user", text);
    chatInput.value = "";
    showTyping();

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, model: selectedModel })
      });
      const data = await res.json();
      removeTyping();

      if (data.reply) {
        appendMessage("bot", data.reply);
      } else {
        appendMessage("bot", "⚠️ Ошибка получения ответа от сервера.");
      }
    } catch (e) {
      removeTyping();
      appendMessage("bot", `⚠️ Сетевая ошибка: ${e.message}`);
    }
  }

  sendBtn.addEventListener("click", sendMessage);
  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
}

// -------------------------------------------------------------
// 3. Самонастройка (Config Center)
// -------------------------------------------------------------
async function loadConfig() {
  try {
    const res = await fetch("/api/config");
    const data = await res.json();
    state.config = data;

    // Обновление стиля
    document.querySelectorAll(".style-chip").forEach((chip) => {
      const styleId = chip.getAttribute("data-style");
      chip.classList.toggle("active", styleId === data.style);
    });

    // Обновление температуры
    const slider = document.getElementById("tempSlider");
    const sliderVal = document.getElementById("tempVal");
    if (slider && sliderVal) {
      slider.value = data.temperature;
      sliderVal.textContent = data.temperature;
    }

    // Обновление правил
    renderRules(data.rules || []);
  } catch (err) {
    console.error("Ошибка загрузки настроек:", err);
  }
}

function renderRules(rules) {
  const container = document.getElementById("rulesList");
  if (!container) return;

  if (rules.length === 0) {
    container.innerHTML = '<li style="color: var(--text-secondary); font-size: 13px; text-align: center; padding: 10px;">Кастомных правил пока нет</li>';
    return;
  }

  container.innerHTML = rules.map((r, i) => `
    <li class="rule-item">
      <span>${i + 1}. ${r}</span>
      <button class="rule-del-btn" onclick="deleteRule(${i + 1})">✕</button>
    </li>
  `).join("");
}

async function updateConfigParam(params) {
  try {
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params)
    });
    const updated = await res.json();
    state.config = updated;
    loadConfig();
  } catch (e) {
    console.error("Ошибка обновления настроек:", e);
  }
}

window.deleteRule = async function(index) {
  await updateConfigParam({ action: "delete_rule", query: index });
};

function setupConfig() {
  // Выбор стиля
  document.querySelectorAll(".style-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const styleId = chip.getAttribute("data-style");
      updateConfigParam({ action: "set_style", style: styleId });
    });
  });

  // Слайдер температуры
  const slider = document.getElementById("tempSlider");
  const sliderVal = document.getElementById("tempVal");
  if (slider && sliderVal) {
    slider.addEventListener("input", (e) => {
      sliderVal.textContent = e.target.value;
    });
    slider.addEventListener("change", (e) => {
      updateConfigParam({ action: "set_temp", temperature: parseFloat(e.target.value) });
    });
  }

  // Добавление правила
  const addBtn = document.getElementById("btnAddRule");
  const addInput = document.getElementById("ruleInput");
  if (addBtn && addInput) {
    addBtn.addEventListener("click", () => {
      const ruleText = addInput.value.trim();
      if (!ruleText) return;
      updateConfigParam({ action: "add_rule", rule: ruleText });
      addInput.value = "";
    });
  }

  // Кнопка сброса
  const resetBtn = document.getElementById("btnResetConfig");
  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      if (confirm("Сбросить все настройки бота к заводским значениям?")) {
        updateConfigParam({ action: "reset_all" });
      }
    });
  }
}

// -------------------------------------------------------------
// 4. Задачи (Todo Tasks)
// -------------------------------------------------------------
async function loadTasks() {
  const container = document.getElementById("tasksList");
  if (!container) return;

  try {
    const res = await fetch("/api/tasks");
    const data = await res.json();
    state.tasks = data.tasks || [];

    if (state.tasks.length === 0) {
      container.innerHTML = '<div style="color: var(--text-secondary); text-align: center; padding: 20px;">Нет активных задач</div>';
      return;
    }

    container.innerHTML = state.tasks.map((task) => `
      <div class="task-item ${task.done ? 'done' : ''}">
        <input type="checkbox" class="task-checkbox" ${task.done ? 'checked' : ''} onchange="toggleTask(${task.id})">
        <span class="task-title">${task.title}</span>
      </div>
    `).join("");
  } catch (err) {
    console.error("Ошибка загрузки задач:", err);
  }
}

window.toggleTask = async function(taskId) {
  try {
    await fetch("/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "toggle", id: taskId })
    });
    loadTasks();
  } catch (e) {
    console.error("Ошибка переключения задачи:", e);
  }
};

function setupTasks() {
  const btn = document.getElementById("btnAddTask");
  const input = document.getElementById("taskInput");

  if (btn && input) {
    btn.addEventListener("click", async () => {
      const title = input.value.trim();
      if (!title) return;

      await fetch("/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "add", title })
      });
      input.value = "";
      loadTasks();
    });
  }
}

// -------------------------------------------------------------
// 5. Обработка PWA Установки (Install Prompt)
// -------------------------------------------------------------
function setupInstall() {
  const btnInstall = document.getElementById("btnInstallApp");
  const modal = document.getElementById("installModal");
  const btnPrimary = document.getElementById("btnModalInstall");
  const btnClose = document.getElementById("btnCloseModal");
  const stepsContainer = document.getElementById("installSteps");

  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
  const isStandalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone;

  // Если приложение уже открыто из иконки на рабочем столе
  if (isStandalone && btnInstall) {
    btnInstall.style.display = "none";
  }

  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    state.deferredPrompt = e;
    if (btnInstall) btnInstall.style.display = "flex";
  });

  function showInstallModal() {
    if (!modal) return;
    if (isIOS) {
      stepsContainer.innerHTML = "1. Нажмите кнопку <strong>«Поделиться»</strong> (значок со стрелкой внизу Safari).<br>2. Прокрутите меню и выберите <strong>«На экран «Домой»</strong>.<br>3. Нажмите <strong>«Добавить»</strong> в правом верхнем углу.";
      if (btnPrimary) btnPrimary.style.display = "none";
    } else if (state.deferredPrompt) {
      stepsContainer.innerHTML = "Нажмите кнопку «Установить» ниже, чтобы добавить приложение на рабочий стол вашего телефона или компьютера.";
      if (btnPrimary) btnPrimary.style.display = "block";
    } else {
      stepsContainer.innerHTML = "Откройте меню браузера (три точки) и выберите <strong>«Установить приложение»</strong> или <strong>«Добавить на главный экран»</strong>.";
      if (btnPrimary) btnPrimary.style.display = "none";
    }
    modal.classList.add("show");
  }

  if (btnInstall) btnInstall.addEventListener("click", showInstallModal);
  if (btnClose) btnClose.addEventListener("click", () => modal.classList.remove("show"));

  if (btnPrimary) {
    btnPrimary.addEventListener("click", async () => {
      if (state.deferredPrompt) {
        state.deferredPrompt.prompt();
        const choice = await state.deferredPrompt.userChoice;
        if (choice.outcome === "accepted") {
          console.log("PWA install accepted!");
          if (btnInstall) btnInstall.style.display = "none";
        }
        state.deferredPrompt = null;
        modal.classList.remove("show");
      }
    });
  }
}

// Запуск инициализации при загрузке DOM
document.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  setupChat();
  setupConfig();
  setupTasks();
  setupInstall();
});

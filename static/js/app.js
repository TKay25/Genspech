const quoteForm = document.getElementById("quoteForm");
const result = document.getElementById("result");
const year = document.getElementById("year");

const chatToggle = document.getElementById("chatToggle");
const chatPanel = document.getElementById("chatPanel");
const chatMessages = document.getElementById("chatMessages");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const chatName = document.getElementById("chatName");
const chatPhone = document.getElementById("chatPhone");

const WHATSAPP_NUMBER = "263718029974";

let chatContext = {
  machine: null,
  days: null,
  urgency: "standard",
};

year.textContent = new Date().getFullYear();

function buildWhatsAppLink(message) {
  return `https://wa.me/${WHATSAPP_NUMBER}?text=${encodeURIComponent(message)}`;
}

function addMessage(text, sender) {
  const node = document.createElement("div");
  node.className = `msg ${sender}`;
  node.textContent = text;
  chatMessages.appendChild(node);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

chatToggle.addEventListener("click", () => {
  const isHidden = chatPanel.hasAttribute("hidden");
  if (isHidden) {
    chatPanel.removeAttribute("hidden");
    chatInput.focus();
    if (!chatMessages.children.length) {
      addMessage("Hi. I can generate a quotation. Tell me machine type, days, and urgency.", "bot");
    }
  } else {
    chatPanel.setAttribute("hidden", "hidden");
  }
});

quoteForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const machine = document.getElementById("machine").value;
  const days = Number(document.getElementById("days").value);
  const urgency = document.getElementById("urgency").value;
  const name = document.getElementById("name").value.trim();
  const phone = document.getElementById("phone").value.trim();

  if (!machine || !days || days < 1 || !urgency || !name || !phone) {
    result.style.display = "block";
    result.textContent = "Please complete all fields to generate an estimate.";
    return;
  }

  try {
    const response = await fetch("/api/quote", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ machine, days, urgency, name, phone }),
    });

    const data = await response.json();

    if (!response.ok || !data.ok) {
      throw new Error(data.error || "Could not generate quote");
    }

    const quote = data.quote;
    const quoteId = data.quoteId;
    const message = [
      `Client: ${name}`,
      `Phone: ${phone}`,
      `Quote ID: ${quoteId}`,
      `Service: ${quote.machineName}`,
      `Duration: ${quote.days} day(s)`,
      `Urgency: ${quote.urgency}`,
      `Estimated Total: $${quote.total.toFixed(2)}`,
    ].join("\n");

    const whatsappLink = buildWhatsAppLink(message);

    result.style.display = "block";
    result.innerHTML = `<strong>Estimate Ready</strong><br><pre>${message}</pre><div class="result-actions"><a class="btn btn-ghost" href="mailto:genspechinvest@gmail.com?subject=Hire%20Request%20-%20${encodeURIComponent(quote.machineName)}&body=${encodeURIComponent(message)}">Email This Request</a><a class="btn btn-primary" href="${whatsappLink}" target="_blank" rel="noopener noreferrer">Send On WhatsApp</a></div>`;
  } catch (error) {
    result.style.display = "block";
    result.textContent = error.message;
  }
});

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = chatInput.value.trim();

  if (!message) {
    return;
  }

  addMessage(message, "user");
  chatInput.value = "";

  try {
    const name = chatName ? chatName.value.trim() : "";
    const phone = chatPhone ? chatPhone.value.trim() : "";

    const response = await fetch("/api/chatbot", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, context: chatContext, name, phone }),
    });

    const data = await response.json();

    if (!response.ok || !data.ok) {
      throw new Error(data.error || "Chatbot is unavailable right now");
    }

    chatContext = data.context || chatContext;
    addMessage(data.response, "bot");

    if (data.quote) {
      const quoteText = [
        `Quote ID: ${data.quoteId}`,
        `Service: ${data.quote.machineName}`,
        `Duration: ${data.quote.days} day(s)`,
        `Urgency: ${data.quote.urgency}`,
        `Estimated Total: $${data.quote.total.toFixed(2)}`,
      ].join("\n");
      addMessage(quoteText, "bot");

      const whatsappLink = buildWhatsAppLink(quoteText);
      addMessage(`Open WhatsApp to continue: ${whatsappLink}`, "bot");
    }
  } catch (error) {
    addMessage(error.message, "bot");
  }
});

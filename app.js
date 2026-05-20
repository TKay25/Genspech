const rates = {
  generator: 180,
  "self-loader": 420,
  "boom-pump": 650,
  "static-pump": 480,
  "power-float": 120,
  poker: 90,
};

const urgencyMultiplier = {
  standard: 1,
  priority: 1.15,
  urgent: 1.3,
};

const machineNames = {
  generator: "Generator Hire",
  "self-loader": "Self Loading Concrete Mixer",
  "boom-pump": "Boom Pump",
  "static-pump": "Static Pump",
  "power-float": "Power Float",
  poker: "Poker Vibrator",
};

const quoteForm = document.getElementById("quoteForm");
const result = document.getElementById("result");
const year = document.getElementById("year");

year.textContent = new Date().getFullYear();

quoteForm.addEventListener("submit", (event) => {
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

  const dailyRate = rates[machine];
  const subtotal = dailyRate * days;
  const total = subtotal * urgencyMultiplier[urgency];

  const message = [
    `Client: ${name}`,
    `Phone: ${phone}`,
    `Service: ${machineNames[machine]}`,
    `Duration: ${days} day(s)`,
    `Urgency: ${urgency}`,
    `Estimated Total: $${total.toFixed(2)}`,
  ].join("\n");

  result.style.display = "block";
  result.innerHTML = `<strong>Estimate Ready</strong><br><pre>${message}</pre><a class="btn ghost" href="mailto:genspechinvest@gmail.com?subject=Hire%20Request%20-%20${encodeURIComponent(machineNames[machine])}&body=${encodeURIComponent(message)}">Email This Request</a>`;
});

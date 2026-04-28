const protocols = [
  { name: "ACL Reconstruction — Patellar Tendon Autograft", category: "Knee", type: "postop", url: "" },
  { name: "ACL Reconstruction — Hamstring Autograft", category: "Knee", type: "postop", url: "" },
  { name: "Meniscal Repair — Medial", category: "Knee", type: "postop", url: "" },
  { name: "Patellofemoral Pain Syndrome", category: "Knee", type: "nonop", url: "" },
  { name: "Total Knee Arthroplasty — Standard", category: "Knee", type: "postop", url: "" },
  { name: "Rotator Cuff Repair — Small Tear", category: "Shoulder", type: "postop", url: "" },
  { name: "Rotator Cuff Repair — Large Tear", category: "Shoulder", type: "postop", url: "" },
  { name: "Shoulder Instability — Anterior Bankart", category: "Shoulder", type: "postop", url: "" },
  { name: "Subacromial Impingement", category: "Shoulder", type: "nonop", url: "" },
  { name: "SLAP Repair", category: "Shoulder", type: "postop", url: "" },
  { name: "THA — Posterior Approach", category: "Hip", type: "postop", url: "" },
  { name: "THA — Anterior Approach", category: "Hip", type: "postop", url: "" },
  { name: "Hip Labral Repair", category: "Hip", type: "postop", url: "" },
  { name: "Femoroacetabular Impingement", category: "Hip", type: "nonop", url: "" },
  { name: "Gluteal Tendinopathy", category: "Hip", type: "nonop", url: "" },
  { name: "Lumbar Fusion — 1–2 Levels", category: "Spine", type: "postop", url: "" },
  { name: "Lumbar Disc Herniation", category: "Spine", type: "nonop", url: "" },
  { name: "Cervical Radiculopathy", category: "Spine", type: "nonop", url: "" },
  { name: "Thoracic Outlet Syndrome", category: "Spine", type: "nonop", url: "" },
  { name: "Spine Return to Running", category: "Spine", type: "return-to-sport", url: "" },
  { name: "Achilles Tendinopathy", category: "Ankle/Foot", type: "nonop", url: "" },
  { name: "Achilles Repair — Acute Rupture", category: "Ankle/Foot", type: "postop", url: "" },
  { name: "Lateral Ankle Sprain — Grade II", category: "Ankle/Foot", type: "nonop", url: "" },
  { name: "Ankle Arthrodesis Rehabilitation", category: "Ankle/Foot", type: "postop", url: "" },
  { name: "Plantar Fasciitis", category: "Ankle/Foot", type: "nonop", url: "" },
  { name: "Medial Epicondylitis", category: "Elbow", type: "nonop", url: "" },
  { name: "Lateral Epicondylitis", category: "Elbow", type: "nonop", url: "" },
  { name: "UCL Reconstruction — Thrower", category: "Elbow", type: "postop", url: "" },
  { name: "Cubital Tunnel Syndrome", category: "Elbow", type: "nonop", url: "" },
  { name: "Elbow Return to Throwing", category: "Elbow", type: "return-to-sport", url: "" },
  { name: "De Quervain Tenosynovitis", category: "Wrist/Hand", type: "nonop", url: "" },
  { name: "Distal Radius Fracture — ORIF", category: "Wrist/Hand", type: "postop", url: "" },
  { name: "Carpal Tunnel Syndrome", category: "Wrist/Hand", type: "nonop", url: "" },
  { name: "Scaphoid Fracture — Conservative", category: "Wrist/Hand", type: "nonop", url: "" },
  { name: "Thumb UCL Repair — Skier's Thumb", category: "Wrist/Hand", type: "postop", url: "" },
  { name: "Concussion Return to Sport", category: "Other", type: "return-to-sport", url: "" },
  { name: "General Conditioning After Injury", category: "Other", type: "nonop", url: "" },
  { name: "Vestibular Rehabilitation", category: "Other", type: "nonop", url: "" },
  { name: "Postural Reeducation Program", category: "Other", type: "nonop", url: "" },
  { name: "Sports-Specific Return to Training", category: "Other", type: "return-to-sport", url: "" }
];

const resultsContainer = document.getElementById("protocol-results");
const summary = document.getElementById("results-summary");
const searchInput = document.getElementById("protocol-search");

function formatProtocolCard(protocol) {
  const card = document.createElement("article");
  card.className = "protocol-card";

  const title = document.createElement("h4");
  title.textContent = protocol.name;

  const meta = document.createElement("div");
  meta.className = "protocol-meta";

  const category = document.createElement("span");
  category.className = "meta-pill";
  category.textContent = protocol.category;

  const type = document.createElement("span");
  type.className = "meta-pill";
  type.textContent = protocol.type.replace(/-/g, " ");

  meta.append(category, type);

  const link = document.createElement("a");
  link.className = "protocol-link";
  link.textContent = protocol.url ? "View protocol" : "Protocol placeholder";
  link.href = protocol.url || "#";
  link.setAttribute("aria-disabled", protocol.url ? "false" : "true");

  card.append(title, meta, link);
  return card;
}

function renderProtocols(list) {
  resultsContainer.innerHTML = "";
  if (!list.length) {
    summary.textContent = "No matching protocols found. Try a different keyword.";
    return;
  }

  const sorted = [...list].sort((a, b) => a.name.localeCompare(b.name));
  summary.textContent = `Showing ${sorted.length} protocol${sorted.length === 1 ? "" : "s"}.`;

  sorted.forEach(protocol => {
    resultsContainer.appendChild(formatProtocolCard(protocol));
  });
}

function filterProtocols(query) {
  const normalized = query.trim().toLowerCase();
  if (!normalized) {
    renderProtocols(protocols);
    return;
  }

  const filtered = protocols.filter(protocol => {
    return (
      protocol.name.toLowerCase().includes(normalized) ||
      protocol.category.toLowerCase().includes(normalized) ||
      protocol.type.toLowerCase().includes(normalized)
    );
  });

  renderProtocols(filtered);
}

searchInput.addEventListener("input", event => {
  filterProtocols(event.target.value);
});

renderProtocols(protocols);

const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
let apiToken;

async function getSessionToken() {
    const response = await fetch("/api/auth/session-token", {
        method: "POST",
        credentials: "same-origin",
    });
    if (!response.ok) {
        throw new Error(`Could not authorize spot management (${response.status})`);
    }
    const body = await response.json();
    apiToken = body.access_token;
}

async function apiRequest(url, options = {}) {
    if (!apiToken) await getSessionToken();
    const response = await fetch(url, {
        ...options,
        credentials: "same-origin",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken,
            Authorization: `Bearer ${apiToken}`,
            ...options.headers,
        },
    });
    if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.message || body?.error || `${response.status} ${response.statusText}`);
    }
    return response.status === 204 ? null : response.json();
}

function showError(message) {
    const box = document.getElementById("spot-error");
    box.textContent = message;
    box.classList.remove("d-none");
}

function statusBadge(status) {
    const styles = {
        AVAILABLE: "text-bg-success",
        OCCUPIED: "text-bg-danger",
        RESERVED: "text-bg-primary",
        MAINTENANCE: "text-bg-warning",
        BLOCKED: "text-bg-dark",
    };
    const badge = document.createElement("span");
    badge.className = `badge ${styles[status] || "text-bg-secondary"}`;
    badge.textContent = status;
    return badge;
}

function actionButton(label, className, onClick) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `btn btn-sm ${className}`;
    button.textContent = label;
    button.addEventListener("click", onClick);
    return button;
}

function renderSpotRow(spot) {
    const row = document.createElement("tr");
    const number = document.createElement("th");
    number.scope = "row";
    number.textContent = spot.spot_number;
    const type = document.createElement("td");
    type.textContent = spot.vehicle_type;
    const use = document.createElement("td");
    const useBadge = document.createElement("span");
    useBadge.className = `badge ${spot.reservation_only ? "text-bg-primary" : "text-bg-light"}`;
    useBadge.textContent = spot.reservation_only ? "Reservation" : "Regular";
    use.appendChild(useBadge);
    const distance = document.createElement("td");
    distance.textContent = String(spot.distance_from_entry);
    const status = document.createElement("td");
    status.appendChild(statusBadge(spot.status));
    const actions = document.createElement("td");
    actions.className = "d-flex gap-2";
    actions.appendChild(actionButton("Edit", "btn-outline-primary", () => openEdit(spot)));
    actions.appendChild(actionButton("Delete", "btn-outline-danger", async () => {
        if (!confirm(`Delete bay ${spot.spot_number}?`)) return;
        try {
            await apiRequest(`/api/spots/${spot.id}`, { method: "DELETE" });
            await loadSpots();
        } catch (error) {
            showError(error.message);
        }
    }));
    row.append(number, type, use, distance, status, actions);
    return row;
}

async function loadSpots() {
    const tbody = document.querySelector("#spots-table tbody");
    try {
        const spots = await apiRequest("/api/spots");
        tbody.replaceChildren(...spots.map(renderSpotRow));
        document.getElementById("spot-error").classList.add("d-none");
    } catch (error) {
        showError(`Could not load parking bays: ${error.message}`);
    }
}

function openEdit(spot) {
    document.getElementById("edit-spot-id").value = spot.id;
    document.getElementById("edit-spot-number").value = spot.spot_number;
    document.getElementById("edit-spot-type").value = spot.vehicle_type;
    document.getElementById("edit-spot-distance").value = spot.distance_from_entry;
    document.getElementById("edit-spot-status").value = spot.status;
    bootstrap.Modal.getOrCreateInstance(document.getElementById("editSpotModal")).show();
}

document.addEventListener("DOMContentLoaded", () => {
    loadSpots();

    document.getElementById("add-spot-form").addEventListener("submit", async event => {
        event.preventDefault();
        try {
            await apiRequest("/api/spots", {
                method: "POST",
                body: JSON.stringify({
                    spot_number: document.getElementById("add-spot-number").value.trim(),
                    vehicle_type: document.getElementById("add-spot-type").value,
                    distance_from_entry: Number(document.getElementById("add-spot-distance").value),
                }),
            });
            bootstrap.Modal.getOrCreateInstance(document.getElementById("addSpotModal")).hide();
            event.target.reset();
            await loadSpots();
        } catch (error) {
            showError(error.message);
        }
    });

    document.getElementById("edit-spot-form").addEventListener("submit", async event => {
        event.preventDefault();
        const id = document.getElementById("edit-spot-id").value;
        try {
            await apiRequest(`/api/spots/${id}`, {
                method: "PUT",
                body: JSON.stringify({
                    spot_number: document.getElementById("edit-spot-number").value.trim(),
                    vehicle_type: document.getElementById("edit-spot-type").value,
                    distance_from_entry: Number(document.getElementById("edit-spot-distance").value),
                    status: document.getElementById("edit-spot-status").value,
                }),
            });
            bootstrap.Modal.getOrCreateInstance(document.getElementById("editSpotModal")).hide();
            await loadSpots();
        } catch (error) {
            showError(error.message);
        }
    });
});

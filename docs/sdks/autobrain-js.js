/**
 * AutoBrain JavaScript SDK v1
 * Works in Node.js and browsers
 * 
 * Usage:
 *   npm install    # no external deps, uses native fetch
 * 
 * In Node.js: 
 *   const { AutoBrainClient } = require('./autobrain-js.js');
 *   (or use ES modules: import { AutoBrainClient } from './autobrain-js.js')
 */

class AutoBrainError extends Error {
  constructor(status, message) {
    super(`${status}: ${message}`);
    this.name = "AutoBrainError";
    this.status = status;
  }
}

class AutoBrainClient {
  /**
   * @param {string} apiKey - Your API key (starts with abapi_)
   * @param {string} [baseUrl="https://api.autobrain.app/api/v1"] - API base URL
   */
  constructor(apiKey, baseUrl = "https://api.autobrain.app/api/v1") {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.headers = {
      "X-API-Key": apiKey,
      "Accept": "application/json",
      "Content-Type": "application/json"
    };
  }

  async _request(method, path, options = {}) {
    const url = `${this.baseUrl}${path}`;
    const response = await fetch(url, {
      method,
      headers: { ...this.headers, ...options.headers },
      body: options.body ? JSON.stringify(options.body) : undefined
    });

    if (response.status >= 400) {
      const text = await response.text();
      throw new AutoBrainError(response.status, text);
    }

    if (response.status === 204) return null;
    return response.json();
  }

  // ========== VEHICLES ==========

  /** @returns {Promise<Array<{id, nickname, make, model, year, odometer_km, rego}>>} */
  async listVehicles() {
    return this._request("GET", "/vehicles");
  }

  /** @param {string} vehicleId */
  async getVehicle(vehicleId) {
    return this._request("GET", `/vehicles/${vehicleId}`);
  }

  /** @param {Object} data - VehicleCreate fields */
  async createVehicle(data) {
    return this._request("POST", "/vehicles", { body: data });
  }

  /** @param {string} vehicleId @param {Object} data - VehicleUpdate fields */
  async updateVehicle(vehicleId, data) {
    return this._request("PATCH", `/vehicles/${vehicleId}`, { body: data });
  }

  /** @param {string} vehicleId */
  async deleteVehicle(vehicleId) {
    return this._request("DELETE", `/vehicles/${vehicleId}`);
  }

  /** @param {string} vehicleId @returns {Promise<Array>} */
  async getTimeline(vehicleId) {
    return this._request("GET", `/vehicles/${vehicleId}/timeline`);
  }

  // ========== SERVICES ==========

  /** @param {string} vehicleId @returns {Promise<Array>} */
  async listServices(vehicleId) {
    return this._request("GET", `/vehicles/${vehicleId}/services`);
  }

  /** @param {string} vehicleId @param {string} serviceId */
  async getService(vehicleId, serviceId) {
    return this._request("GET", `/vehicles/${vehicleId}/services/${serviceId}`);
  }

  /** @param {string} vehicleId @param {Object} data */
  async createService(vehicleId, data) {
    return this._request("POST", `/vehicles/${vehicleId}/services`, { body: data });
  }

  /** @param {string} vehicleId @param {string} serviceId @param {Object} data */
  async updateService(vehicleId, serviceId, data) {
    return this._request("PATCH", `/vehicles/${vehicleId}/services/${serviceId}`, { body: data });
  }

  /** @param {string} vehicleId @param {string} serviceId */
  async deleteService(vehicleId, serviceId) {
    return this._request("DELETE", `/vehicles/${vehicleId}/services/${serviceId}`);
  }

  // ========== FUEL ==========

  /** @param {string} vehicleId @param {number} [fy] Australian financial year */
  async listFuel(vehicleId, fy) {
    const params = fy ? `?fy=${fy}` : "";
    return this._request("GET", `/vehicles/${vehicleId}/fuel${params}`);
  }

  /** @param {string} vehicleId @param {Object} data */
  async addFuel(vehicleId, data) {
    return this._request("POST", `/vehicles/${vehicleId}/fuel`, { body: data });
  }

  /** @param {string} vehicleId @param {string} fuelId @param {Object} data */
  async updateFuel(vehicleId, fuelId, data) {
    return this._request("PATCH", `/vehicles/${vehicleId}/fuel/${fuelId}`, { body: data });
  }

  /** @param {string} vehicleId @param {string} fuelId */
  async deleteFuel(vehicleId, fuelId) {
    return this._request("DELETE", `/vehicles/${vehicleId}/fuel/${fuelId}`);
  }

  /** @param {string} vehicleId */
  async getFuelStats(vehicleId) {
    return this._request("GET", `/vehicles/${vehicleId}/fuel/stats`);
  }

  // ========== DIAGNOSTICS ==========

  /** @param {string} vehicleId @param {Object} data */
  async runDiagnostics(vehicleId, data) {
    return this._request("POST", `/vehicles/${vehicleId}/diagnostics`, { body: data });
  }

  /** @param {string} vehicleId @returns {Promise<Array>} */
  async listDiagnostics(vehicleId) {
    return this._request("GET", `/vehicles/${vehicleId}/diagnostics`);
  }

  // ========== LOGBOOK ==========

  /** @param {string} vehicleId @param {number} [fy] */
  async listLogbook(vehicleId, fy) {
    const params = fy ? `?fy=${fy}` : "";
    return this._request("GET", `/vehicles/${vehicleId}/logbook${params}`);
  }

  /** @param {string} vehicleId @param {Object} data */
  async startTrip(vehicleId, data) {
    return this._request("POST", `/vehicles/${vehicleId}/logbook`, { body: data });
  }

  /** @param {string} vehicleId @param {string} entryId @param {Object} data */
  async updateTrip(vehicleId, entryId, data) {
    return this._request("PATCH", `/vehicles/${vehicleId}/logbook/${entryId}`, { body: data });
  }

  // ========== WEBHOOKS ==========

  /** @returns {Promise<Array>} */
  async listWebhooks() {
    return this._request("GET", "/developer/webhooks");
  }

  /**
   * @param {string} label
   * @param {string} url
   * @param {string[]} events
   * @param {number} [maxRetries=5]
   */
  async createWebhook(label, url, events, maxRetries = 5) {
    return this._request("POST", "/developer/webhooks", {
      body: { label, url, events, max_retries: maxRetries }
    });
  }

  /** @param {string} webhookId */
  async deleteWebhook(webhookId) {
    return this._request("DELETE", `/developer/webhooks/${webhookId}`);
  }
}

// Export for both CommonJS and ES Modules
if (typeof module !== "undefined" && module.exports) {
  module.exports = { AutoBrainClient, AutoBrainError };
}

// ========== EXAMPLE USAGE ==========
// Run with: node autobrain-js.js
if (typeof require !== "undefined" && require.main === module) {
  (async () => {
    const apiKey = process.env.AUTOBRAIN_API_KEY;
    if (!apiKey) {
      console.error("Set AUTOBRAIN_API_KEY environment variable");
      process.exit(1);
    }

    const client = new AutoBrainClient(apiKey);

    try {
      // List vehicles
      const vehicles = await client.listVehicles();
      console.log(`Found ${vehicles.length} vehicles:`);
      for (const v of vehicles) {
        console.log(`  - ${v.nickname} (${v.make} ${v.model} ${v.year}) - ${v.odometer_km}km`);
      }

      // Add fuel to first vehicle
      if (vehicles.length > 0) {
        const v = vehicles[0];
        const fuel = await client.addFuel(v.id, {
          litres: 45.5,
          price_per_litre: 1.89,
          odometer_km: v.odometer_km || 0
        });
        console.log(`\nAdded fuel: ${fuel.litres}L @ $${fuel.price_per_litre}/L = $${fuel.total_cost}`);
      }

      // List recent services
      for (const v of vehicles.slice(0, 1)) {
        const services = await client.listServices(v.id);
        console.log(`\nServices for ${v.nickname}:`);
        for (const s of services.slice(0, 3)) {
          console.log(`  - ${s.service_date}: ${s.service_type} ($${s.cost})`);
        }
      }

    } catch (err) {
      console.error("Error:", err.message);
      process.exit(1);
    }
  })();
}
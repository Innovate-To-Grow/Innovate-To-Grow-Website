// Retired standalone asset. ALTCHA's UMD bundle embeds its own workers.
// Keep this inert file so static uploads overwrite previously deployed copies.
if (typeof WorkerGlobalScope !== "undefined" && self instanceof WorkerGlobalScope) {
  self.close();
}

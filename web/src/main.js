import { runHouseViewer } from './house_viewer.js';

runHouseViewer().catch((error) => {
  console.error(error);
  document.body.innerHTML = `
    <main style="padding: 24px; font-family: sans-serif;">
      <h1>Failed to load house viewer</h1>
      <pre>${String(error.message || error)}</pre>
    </main>
  `;
});

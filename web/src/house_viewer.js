import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

const FLOOR_Y = 0.01;
const WALL_THICKNESS = 0.08;
const MOVE_PLANE = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
const ROTATION_STEP = 90;

function colorFromString(value) {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = value.charCodeAt(index) + ((hash << 5) - hash);
  }

  const hue = Math.abs(hash) % 360;
  return new THREE.Color(`hsl(${hue} 55% 58%)`);
}

function deepClone(data) {
  return JSON.parse(JSON.stringify(data));
}

function formatVector3(vector) {
  return `${vector.x.toFixed(2)}, ${vector.y.toFixed(2)}, ${vector.z.toFixed(2)}`;
}

function polygonToShape(points) {
  const shape = new THREE.Shape();
  points.forEach((point, index) => {
    if (index === 0) {
      shape.moveTo(point.x, point.z);
      return;
    }
    shape.lineTo(point.x, point.z);
  });
  shape.closePath();
  return shape;
}

function computeSceneBounds(data) {
  const xs = [];
  const zs = [];

  for (const room of data.rooms) {
    for (const point of room.floorPolygon) {
      xs.push(point.x);
      zs.push(point.z);
    }
  }

  if (!xs.length || !zs.length) {
    return { centerX: 0, centerZ: 0, size: 10 };
  }

  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minZ = Math.min(...zs);
  const maxZ = Math.max(...zs);

  return {
    centerX: (minX + maxX) / 2,
    centerZ: (minZ + maxZ) / 2,
    size: Math.max(maxX - minX, maxZ - minZ, 6),
  };
}

function createShell() {
  document.body.innerHTML = `
    <div class="app-shell">
      <aside class="sidebar">
        <div>
          <p class="eyebrow">ProcTHOR Viewer</p>
          <h1>House Layout Editor</h1>
          <p class="lede">Box-based viewer for rooms, walls, and furniture with simple rearrangement.</p>
        </div>
        <div class="panel">
          <h2>Controls</h2>
          <p>Drag furniture on the floor plane. Use rotate to turn the selected item by 90 degrees.</p>
          <button id="rotate-button" disabled>Rotate 90°</button>
          <button id="export-button">Export Edited JSON</button>
        </div>
        <div class="panel">
          <h2>Selection</h2>
          <div id="selection-details">Select a furniture box to inspect and edit it.</div>
        </div>
        <div class="panel">
          <h2>Scene</h2>
          <div id="scene-stats">Loading…</div>
        </div>
      </aside>
      <main class="viewport">
        <div id="canvas-root"></div>
      </main>
    </div>
  `;

  return {
    canvasRoot: document.getElementById('canvas-root'),
    rotateButton: document.getElementById('rotate-button'),
    exportButton: document.getElementById('export-button'),
    selectionDetails: document.getElementById('selection-details'),
    sceneStats: document.getElementById('scene-stats'),
  };
}

function updateSelectionPanel(elements, selectedObject) {
  if (!selectedObject) {
    elements.selectionDetails.textContent = 'Select a furniture box to inspect and edit it.';
    elements.rotateButton.disabled = true;
    return;
  }

  elements.rotateButton.disabled = false;
  elements.selectionDetails.innerHTML = `
    <p><strong>${selectedObject.objectType}</strong></p>
    <p>ID: ${selectedObject.id}</p>
    <p>Asset: ${selectedObject.assetId}</p>
    <p>Position: ${formatVector3(selectedObject.position)}</p>
    <p>Rotation: ${formatVector3(selectedObject.rotation)}</p>
    <p>Size: ${formatVector3(selectedObject.size)}</p>
    <p>Kinematic: ${selectedObject.kinematic ? 'true' : 'false'}</p>
  `;
}

function updateSceneStats(elements, data) {
  elements.sceneStats.innerHTML = `
    <p>Rooms: ${data.rooms.length}</p>
    <p>Walls: ${data.walls.length}</p>
    <p>Objects: ${data.objects.length}</p>
    <p>Doors: ${data.doors.length}</p>
    <p>Windows: ${data.windows.length}</p>
  `;
}

function createRenderer(canvasRoot) {
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(canvasRoot.clientWidth, canvasRoot.clientHeight);
  renderer.shadowMap.enabled = true;
  canvasRoot.appendChild(renderer.domElement);
  return renderer;
}

function createRoomMesh(room) {
  const geometry = new THREE.ShapeGeometry(polygonToShape(room.floorPolygon));
  geometry.rotateX(-Math.PI / 2);

  return new THREE.Mesh(
    geometry,
    new THREE.MeshStandardMaterial({
      color: colorFromString(room.roomType),
      transparent: true,
      opacity: 0.75,
      side: THREE.DoubleSide,
    }),
  );
}

function createWallMesh(wall) {
  const [start, end, topStart, topEnd] = wall.polygon;
  const length = Math.hypot(end.x - start.x, end.z - start.z);
  const height = Math.max(topStart.y, topEnd.y) - Math.min(start.y, end.y);

  const geometry = new THREE.BoxGeometry(length || 0.01, height || 0.01, WALL_THICKNESS);
  const material = new THREE.MeshStandardMaterial({
    color: wall.empty ? '#d2d6db' : '#c9c1b5',
  });
  const mesh = new THREE.Mesh(geometry, material);

  const angle = Math.atan2(end.z - start.z, end.x - start.x);
  mesh.rotation.y = -angle;
  mesh.position.set(
    (start.x + end.x) / 2,
    Math.min(start.y, end.y) + height / 2,
    (start.z + end.z) / 2,
  );
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  return mesh;
}

function createObjectMesh(object) {
  const geometry = new THREE.BoxGeometry(object.size.x, object.size.y, object.size.z);
  const material = new THREE.MeshStandardMaterial({
    color: colorFromString(object.objectType),
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  mesh.position.set(object.position.x, object.position.y, object.position.z);
  mesh.rotation.set(
    THREE.MathUtils.degToRad(object.rotation.x),
    THREE.MathUtils.degToRad(object.rotation.y),
    THREE.MathUtils.degToRad(object.rotation.z),
  );
  mesh.userData.objectId = object.id;
  return mesh;
}

function downloadJson(filename, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export async function runHouseViewer() {
  const elements = createShell();
  const response = await fetch('/data/house.json');
  if (!response.ok) {
    throw new Error(`Failed to load /data/house.json (${response.status})`);
  }

  const sourceData = await response.json();
  const editableData = deepClone(sourceData);

  updateSceneStats(elements, editableData);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#f4efe5');
  scene.add(new THREE.AmbientLight('#ffffff', 1.8));

  const directionalLight = new THREE.DirectionalLight('#fff5df', 1.8);
  directionalLight.position.set(8, 12, 4);
  directionalLight.castShadow = true;
  scene.add(directionalLight);

  const bounds = computeSceneBounds(editableData);
  const camera = new THREE.PerspectiveCamera(
    55,
    elements.canvasRoot.clientWidth / elements.canvasRoot.clientHeight,
    0.1,
    1000,
  );
  camera.position.set(bounds.centerX + bounds.size, bounds.size * 1.1, bounds.centerZ + bounds.size);

  const renderer = createRenderer(elements.canvasRoot);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(bounds.centerX, 0, bounds.centerZ);
  controls.enableDamping = true;
  controls.maxPolarAngle = Math.PI / 2.05;
  controls.update();

  scene.add(new THREE.GridHelper(bounds.size * 1.8, Math.max(10, Math.round(bounds.size * 2)), '#6f7b7f', '#c7c1b4'));

  const roomGroup = new THREE.Group();
  const wallGroup = new THREE.Group();
  const objectGroup = new THREE.Group();
  scene.add(roomGroup, wallGroup, objectGroup);

  for (const room of editableData.rooms) {
    const mesh = createRoomMesh(room);
    mesh.position.y = FLOOR_Y;
    roomGroup.add(mesh);
  }

  for (const wall of editableData.walls) {
    wallGroup.add(createWallMesh(wall));
  }

  const objectIndex = new Map(editableData.objects.map((object) => [object.id, object]));
  const objectMeshIndex = new Map();

  for (const object of editableData.objects) {
    const mesh = createObjectMesh(object);
    objectMeshIndex.set(object.id, mesh);
    objectGroup.add(mesh);
  }

  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  const dragPoint = new THREE.Vector3();
  let selectedId = null;
  let dragging = false;
  let dragOffset = new THREE.Vector3();

  function syncMeshFromObject(objectId) {
    const object = objectIndex.get(objectId);
    const mesh = objectMeshIndex.get(objectId);
    if (!object || !mesh) {
      return;
    }

    mesh.position.set(object.position.x, object.position.y, object.position.z);
    mesh.rotation.set(
      THREE.MathUtils.degToRad(object.rotation.x),
      THREE.MathUtils.degToRad(object.rotation.y),
      THREE.MathUtils.degToRad(object.rotation.z),
    );
  }

  function setSelection(objectId) {
    selectedId = objectId;

    for (const [id, mesh] of objectMeshIndex.entries()) {
      const object = objectIndex.get(id);
      const color = id === selectedId ? '#d85f3d' : colorFromString(object.objectType);
      mesh.material.color.set(color);
    }

    updateSelectionPanel(elements, selectedId ? objectIndex.get(selectedId) : null);
  }

  function toPointerPosition(event) {
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  }

  function pickObject(event) {
    toPointerPosition(event);
    raycaster.setFromCamera(pointer, camera);
    const intersections = raycaster.intersectObjects([...objectMeshIndex.values()]);
    return intersections[0] || null;
  }

  renderer.domElement.addEventListener('pointerdown', (event) => {
    const hit = pickObject(event);
    if (!hit) {
      setSelection(null);
      dragging = false;
      return;
    }

    const objectId = hit.object.userData.objectId;
    setSelection(objectId);

    raycaster.setFromCamera(pointer, camera);
    if (raycaster.ray.intersectPlane(MOVE_PLANE, dragPoint)) {
      const object = objectIndex.get(objectId);
      dragOffset.set(
        object.position.x - dragPoint.x,
        0,
        object.position.z - dragPoint.z,
      );
      dragging = true;
    }
  });

  window.addEventListener('pointerup', () => {
    dragging = false;
  });

  window.addEventListener('pointermove', (event) => {
    if (!dragging || !selectedId) {
      return;
    }

    toPointerPosition(event);
    raycaster.setFromCamera(pointer, camera);
    if (!raycaster.ray.intersectPlane(MOVE_PLANE, dragPoint)) {
      return;
    }

    const object = objectIndex.get(selectedId);
    object.position.x = dragPoint.x + dragOffset.x;
    object.position.z = dragPoint.z + dragOffset.z;
    syncMeshFromObject(selectedId);
    updateSelectionPanel(elements, object);
  });

  elements.rotateButton.addEventListener('click', () => {
    if (!selectedId) {
      return;
    }
    const object = objectIndex.get(selectedId);
    object.rotation.y = (object.rotation.y + ROTATION_STEP) % 360;
    syncMeshFromObject(selectedId);
    updateSelectionPanel(elements, object);
  });

  elements.exportButton.addEventListener('click', () => {
    downloadJson('house.edited.json', editableData);
  });

  function onResize() {
    const width = elements.canvasRoot.clientWidth;
    const height = elements.canvasRoot.clientHeight;
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height);
  }

  window.addEventListener('resize', onResize);
  onResize();

  function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  }

  animate();
}

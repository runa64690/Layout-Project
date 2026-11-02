import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

// Corrections are XYZ Euler angles in degrees. Align semantic directions with
// the catalog: the bed's pillow_side WEST means local -X, not generic +Z.
export const MODEL_REGISTRY = {
  shelf: { url: `${import.meta.env?.BASE_URL ?? '/'}models/bookcase-open.glb`, rotationCorrection: [0, 0, 0] },
  // Kenney bedSingle's pillow is at -Z. +90 degrees around Y moves it to -X.
  bed: { url: `${import.meta.env?.BASE_URL ?? '/'}models/bed-single.glb`, rotationCorrection: [0, 90, 0] },
  // API front is NORTH (+plan Y = -Three Z). Put the backrest at +Z.
  chair: { url: `${import.meta.env?.BASE_URL ?? '/'}models/chair.glb`, rotationCorrection: [0, 180, 0] },
  table: { url: `${import.meta.env?.BASE_URL ?? '/'}models/table-coffee-square.glb`, rotationCorrection: [0, 0, 0] },
  // The catalog ID is tv_unit (Unity's custom "TV" entry is not an API ID).
  // The original screen faces +Z; NORTH/front in the Web scene is -Z.
  tv_unit: { url: `${import.meta.env?.BASE_URL ?? '/'}models/television-modern.glb`, rotationCorrection: [0, 180, 0] },
};

function disposeAsset(root) {
  const geometries = new Set(), materials = new Set(), textures = new Set();
  root.traverse(object => {
    if (object.geometry) geometries.add(object.geometry);
    for (const material of object.material ? [].concat(object.material) : []) {
      materials.add(material);
      for (const value of Object.values(material)) if (value?.isTexture) textures.add(value);
    }
  });
  for (const item of [...geometries, ...materials, ...textures]) item.dispose();
}

export function normalizeModel(source, correction = [0, 0, 0]) {
  const oriented = new THREE.Group();
  oriented.rotation.set(...correction.map(THREE.MathUtils.degToRad));
  oriented.add(source);
  oriented.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(oriented), size = box.getSize(new THREE.Vector3());
  if (![size.x, size.y, size.z].every(n => Number.isFinite(n) && n > .0001)) throw new Error('Model has invalid bounds');
  // A unit-size template whose origin is its bottom center.
  const fit = new THREE.Group();
  fit.scale.set(1 / size.x, 1 / size.y, 1 / size.z);
  fit.position.set(-(box.min.x + box.max.x) / (2 * size.x), -box.min.y / size.y, -(box.min.z + box.max.z) / (2 * size.z));
  fit.add(oriented);
  const template = new THREE.Group();
  template.add(fit);
  template.traverse(object => {
    object.userData.sharedModelAsset = true;
    if (object.isMesh) { object.castShadow = true; object.receiveShadow = true; }
  });
  return template;
}

export class FurnitureModels {
  constructor({ registry = MODEL_REGISTRY, load = url => new GLTFLoader().loadAsync(url), onChange = () => {}, onError = () => {} } = {}) {
    Object.assign(this, { registry, load, onChange, onError });
    this.assets = new Map();
    this.templates = new Map();
    this.failed = new Set();
    this.disposed = false;
  }
  request(id) {
    const entry = this.registry[id];
    if (this.disposed || !entry || this.failed.has(id)) return null;
    if (!this.templates.has(id)) {
      this.templates.set(id, null);
      // A URL is fetched once even if several model IDs use it.
      if (!this.assets.has(entry.url)) this.assets.set(entry.url, this.loadAsset(entry.url));
      this.assets.get(entry.url).then(source => {
        if (this.disposed) return;
        try {
          this.templates.set(id, normalizeModel(source.clone(true), entry.rotationCorrection));
        } catch (error) {
          this.failed.add(id); this.onError(id, error);
        }
        this.onChange();
      }).catch(error => {
        if (this.disposed) return;
        this.failed.add(id); this.onError(id, error); this.onChange();
      });
    }
    return this.templates.get(id);
  }
  async loadAsset(url) {
    const gltf = await this.load(url);
    const source = gltf.scene;
    if (this.disposed) { disposeAsset(source); source.userData.assetDisposed = true; }
    return source;
  }
  create(id, definition) {
    const template = this.request(id);
    if (!template) return null;
    const instance = template.clone(true);
    instance.scale.set(definition.width_m, definition.height_m, definition.depth_m);
    return instance;
  }
  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    // Pending loads dispose themselves; fulfilled loads are released here.
    for (const pending of this.assets.values()) pending.then(source => {
      if (!source.userData.assetDisposed) { disposeAsset(source); source.userData.assetDisposed = true; }
    }).catch(() => {});
    this.templates.clear(); this.assets.clear();
  }
}

import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { FBXLoader } from 'three/examples/jsm/loaders/FBXLoader.js';
import { GLTFExporter } from 'three/examples/jsm/exporters/GLTFExporter.js';
import { MeshStandardMaterial } from 'three';

// GLTFExporter uses the browser FileReader interface for binary buffers.
globalThis.FileReader = class {
  readAsArrayBuffer(blob) { blob.arrayBuffer().then(result => { this.result = result; this.onloadend?.(); }); }
  readAsDataURL(blob) { blob.arrayBuffer().then(result => { this.result = `data:${blob.type};base64,${Buffer.from(result).toString('base64')}`; this.onloadend?.(); }); }
};
const source = new URL('../../unity/Assets/KenneyFurniture/bookcaseOpen.fbx', import.meta.url);
const destination = new URL('../public/models/bookcase-open.glb', import.meta.url);
const original = await readFile(source, 'utf8');
// This asset's UV closing brace has one excess tab. Three's ASCII parser is
// indentation-sensitive. Repair only the conversion input, never the Unity file.
const normalized = original.replace(/(\t\t\tUV: \*\d+ \{\r?\n[^\n]+\r?\n)\t\t\t\t\}/, '$1\t\t\t}');
const model = new FBXLoader().parse(new TextEncoder().encode(normalized).buffer, '');
model.traverse(object => {
  if (!object.isMesh) return;
  const convert = material => new MeshStandardMaterial({ name: material.name, color: material.color, roughness: .85, metalness: 0 });
  object.material = Array.isArray(object.material) ? object.material.map(convert) : convert(object.material);
});
model.userData.source = 'Kenney bookcaseOpen.fbx (Unity KennyShelf prefab)';
const binary = await new GLTFExporter().parseAsync(model, { binary: true });
await mkdir(new URL('.', destination), { recursive: true });
await writeFile(destination, Buffer.from(binary));
console.log(`Generated ${destination.pathname} (${binary.byteLength} bytes)`);

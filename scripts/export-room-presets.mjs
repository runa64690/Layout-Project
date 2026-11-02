import { writeFileSync } from 'node:fs';
import { SHAPES,SIZES,preset } from '../web/src/room_geometry.js';

const cases=SHAPES.flatMap(([shape])=>SIZES.map(tatami=>({shape,tatami,vertices:preset(shape,tatami)})));
writeFileSync(new URL('../contracts/room-presets.json',import.meta.url),JSON.stringify(cases,null,2)+'\n');

import { cpSync } from 'node:fs';
cpSync(new URL('../ppt-editor/dist/',import.meta.url),new URL('../dist/ppt-editor/',import.meta.url),{recursive:true});
cpSync(new URL('../public/school-emblem.svg',import.meta.url),new URL('../dist/ppt-editor/school-emblem.svg',import.meta.url));

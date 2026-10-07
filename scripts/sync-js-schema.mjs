// 从唯一权威定义生成发布副本；--check 不修改任何文件。
import {readFile, writeFile} from 'node:fs/promises';

const root = new URL('../', import.meta.url);
for (const [source, target] of [
  ['src/g2a/schema.json', 'sdk/javascript/schema.json'],
  ['LICENSE', 'sdk/javascript/LICENSE'],
]) {
  const data = await readFile(new URL(source, root));
  if (process.argv.includes('--check')) {
    const copy = await readFile(new URL(target, root));
    if (!data.equals(copy)) throw new Error(`Generated artifact out of date: ${target}`);
  } else {
    await writeFile(new URL(target, root), data);
  }
}

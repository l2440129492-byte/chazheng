const test = require('node:test');
const assert = require('node:assert/strict');
const { entries, search } = require('../catalog.js');
test('共享资料包含完整基础检索字段，身份不重复', () => {
  assert.ok(entries.length >= 25);
  assert.equal(new Set(entries.map(e => e.id)).size, entries.length);
  for (const e of entries) {
    assert.ok(e.id && e.name);
    for (const field of ['aliases','characters','versions','profiles','sources']) assert.ok(Array.isArray(e[field]));
    for (const source of e.sources) assert.equal(new URL(source).protocol, 'https:');
  }
});
test('别名、英文大小写、人物、版本可以搜索', () => {
  assert.equal(search('nArUtO','acg')[0].id, 'naruto');
  assert.equal(search('海贼王','acg')[0].id, 'one-piece');
  assert.equal(search('旗木卡卡西','acg')[0].id, 'naruto');
  assert.equal(search('Fate / Zero','acg')[0].id, 'fate');
  assert.equal(search('宪问','wenshi')[0].id, 'analects');
  assert.equal(search('瑞克摇','meme')[0].id, 'rickroll');
});
test('不同分类仍可检索作品，空查询优先当前分类', () => {
  assert.equal(search('论语','acg')[0].id, 'analects');
  assert.equal(search('火影','wenshi')[0].id, 'naruto');
  for (const profile of ['acg','wenshi','meme']) {
    const result = search('', profile);
    assert.equal(result.length, entries.length);
    assert.ok(result[0].profiles.includes(profile));
    const lastPreferred = result.findLastIndex(e => e.profiles.includes(profile));
    assert.ok(result.slice(0,lastPreferred+1).every(e => e.profiles.includes(profile)));
  }
  assert.deepEqual(search('不存在的独特作品','meme'), []);
});
test('手动补充参与搜索且不覆盖基础条目、不污染后续查询', () => {
  const custom = {id:'custom:a',name:'我的资料',aliases:['自定义'],characters:['阿甲'],versions:[],profiles:['meme'],sources:[]};
  assert.equal(search('阿甲','acg',[custom])[0], custom);
  assert.equal(search('自定义','meme',[custom])[0], custom);
  assert.equal(search('阿甲','acg').length, 0);
  assert.equal(search('火影','acg',[{...custom,id:'naruto'}])[0].name, '火影忍者');
});

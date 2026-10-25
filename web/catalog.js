/* Shared discovery context only. Entries and source suggestions are not evidence;
 * claims must still be checked against retrieved original material. */
(function (root) {
  'use strict';
  const item = (id, name, aliases, characters, versions, profiles, sources) =>
    ({ id, name, aliases, characters, versions, profiles, sources });
  const entries = [
    item('naruto','火影忍者',['NARUTO','火影'],['漩涡鸣人','宇智波佐助','旗木卡卡西'],['漫画','电视动画','疾风传'],['acg'],['https://naruto-official.com/']),
    item('one-piece','航海王',['ONE PIECE','海贼王'],['蒙奇·D·路飞','罗罗诺亚·索隆'],['漫画','电视动画','真人剧'],['acg'],['https://one-piece.com/']),
    item('dragon-ball','龙珠',['DRAGON BALL','七龙珠'],['孙悟空','贝吉塔'],['漫画','龙珠Z','龙珠超'],['acg'],['https://dragon-ball-official.com/']),
    item('fate','Fate 系列',['Fate','命运之夜','型月'],['卫宫士郎','阿尔托莉雅','远坂凛'],['Fate/stay night','Fate/Zero','Fate/Grand Order','游戏','动画'],['acg'],['https://www.fate-sn.com/']),
    item('eva','新世纪福音战士',['EVA','Evangelion'],['碇真嗣','绫波丽','明日香'],['电视动画','旧剧场版','新剧场版'],['acg'],['https://www.evangelion.co.jp/']),
    item('conan','名侦探柯南',['Detective Conan','柯南'],['江户川柯南','工藤新一','毛利兰'],['漫画','电视动画','剧场版'],['acg'],['https://www.conan-portal.com/']),
    item('genshin','原神',['Genshin Impact'],['旅行者','派蒙','钟离'],['游戏','角色语音','任务文本'],['acg'],['https://ys.mihoyo.com/']),
    item('star-rail','崩坏：星穹铁道',['星穹铁道','Honkai Star Rail'],['开拓者','三月七','丹恒'],['游戏','任务文本'],['acg'],['https://sr.mihoyo.com/']),
    item('pokemon','宝可梦',['Pokemon','Pokémon','口袋妖怪','神奇宝贝'],['皮卡丘','小智'],['游戏','电视动画','特别篇漫画'],['acg'],['https://www.pokemon.com/']),
    item('jojo','JOJO的奇妙冒险',['JoJo','ジョジョ'],['乔纳森·乔斯达','空条承太郎','迪奥'],['漫画','电视动画'],['acg','meme'],['https://jojo-portal.com/']),
    item('journey-west','西游记',['西游'],['孙悟空','唐僧','猪八戒','沙僧'],['小说','电视剧','动画改编'],['wenshi','acg'],['https://zh.wikisource.org/wiki/西遊記']),
    item('three-kingdoms','三国演义',['三国志通俗演义'],['诸葛亮','刘备','曹操','关羽'],['小说','电视剧','游戏改编'],['wenshi','acg'],['https://zh.wikisource.org/wiki/三國演義']),
    item('dream-red','红楼梦',['石头记'],['贾宝玉','林黛玉','薛宝钗'],['脂本','程本','电视剧'],['wenshi'],['https://zh.wikisource.org/wiki/紅樓夢']),
    item('water-margin','水浒传',['忠义水浒传'],['宋江','林冲','武松'],['七十回本','百回本','百二十回本','电视剧'],['wenshi'],['https://zh.wikisource.org/wiki/水滸傳']),
    item('analects','论语',['論語','Analects'],['孔子','颜回','子路','子贡'],['宪问','学而','为政','集注'],['wenshi'],['https://ctext.org/analects/zh','https://zh.wikisource.org/wiki/論語']),
    item('laozi','道德经',['老子','道德經','Tao Te Ching'],['老子'],['道经','德经','帛书','通行本'],['wenshi'],['https://ctext.org/dao-de-jing/zh']),
    item('zhuangzi','庄子',['莊子'],['庄周'],['内篇','外篇','杂篇','逍遥游'],['wenshi'],['https://ctext.org/zhuangzi/zh']),
    item('mencius','孟子',['Mencius'],['孟轲'],['梁惠王','公孙丑','告子'],['wenshi'],['https://ctext.org/mengzi/zh']),
    item('shiji','史记',['史記','太史公书'],['司马迁'],['本纪','世家','列传'],['wenshi'],['https://ctext.org/shiji/zh']),
    item('shijing','诗经',['詩經'],[],['国风','小雅','大雅','颂'],['wenshi'],['https://ctext.org/book-of-poetry/zh']),
    item('shishuo','世说新语',['世說新語'],['刘义庆'],['德行','言语','雅量'],['wenshi'],['https://zh.wikisource.org/wiki/世說新語']),
    item('liaozhai','聊斋志异',['聊齋誌異'],['蒲松龄'],['小说','影视改编'],['wenshi','acg'],['https://zh.wikisource.org/wiki/聊齋志異']),
    item('rickroll','Rickroll',['瑞克摇','Rickrolling','Never Gonna Give You Up'],['Rick Astley'],['音乐视频','网络迷因'],['meme'],['https://knowyourmeme.com/memes/rickroll']),
    item('doge','Doge',['狗头','柴犬表情','ドージ'],['Kabosu'],['表情包','网络迷因'],['meme'],['https://knowyourmeme.com/memes/doge']),
    item('distracted-boyfriend','分心男友',['Distracted Boyfriend','回头男'],[],['图库照片','表情包'],['meme'],['https://knowyourmeme.com/memes/distracted-boyfriend']),
    item('this-is-fine','This Is Fine',['这很好','一切安好','火中狗'],[],['漫画','表情包'],['meme'],['https://knowyourmeme.com/memes/this-is-fine']),
    item('pepe','Pepe the Frog',['悲伤蛙','佩佩蛙'],['Pepe'],['漫画','表情包'],['meme'],['https://knowyourmeme.com/memes/pepe-the-frog']),
    item('rick-morty','瑞克和莫蒂',['Rick and Morty','瑞克与莫蒂'],['Rick Sanchez','Morty Smith'],['电视动画','网络迷因'],['acg','meme'],['https://www.adultswim.com/videos/rick-and-morty'])
  ];
  const normalize = value => String(value || '').normalize('NFKC').toLocaleLowerCase().replace(/[\s·：:／/\-_]/g, '');
  function search(query, profile, customEntries = []) {
    const q = normalize(query);
    const pool = new Map(entries.map(entry => [entry.id, entry]));
    for (const entry of customEntries) {
      // A user-added entry must have its own identity; do not replace curated entries.
      if (entry && typeof entry.id === 'string' && typeof entry.name === 'string' && !pool.has(entry.id)) pool.set(entry.id, entry);
    }
    return [...pool.values()].map((entry, index) => {
      const name = normalize(entry.name);
      const aliases = (entry.aliases || []).map(normalize);
      const terms = [...aliases, ...(entry.characters || []).map(normalize), ...(entry.versions || []).map(normalize)];
      let relevance = !q ? 1 : name === q ? 100 : aliases.includes(q) ? 90 : name.includes(q) ? 70 : terms.some(term => term.includes(q)) ? 50 : 0;
      return { entry, index, relevance, preferred: (entry.profiles || []).includes(profile) ? 1 : 0 };
    }).filter(row => row.relevance > 0)
      .sort((a, b) => b.preferred - a.preferred || b.relevance - a.relevance || a.index - b.index)
      .map(row => row.entry);
  }
  const api = { entries, search };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.WORK_CATALOG = api;
})(typeof window !== 'undefined' ? window : null);

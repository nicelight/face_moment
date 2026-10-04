import assert from 'node:assert/strict';
import { test } from 'node:test';
import { renderPublicPhotoGallery } from '../../client/public-photo-gallery.js';

test('gallery keeps granted order, uses text safely and never displays common for an unmatched venue', async () => {
  class Element {
    constructor(tag) { this.tag=tag; this.children=[]; this.dataset={}; }
    append(...children) { this.children.push(...children); }
    replaceChildren() { this.children=[]; }
    contains(node) { return this===node || this.children.some(child=>child instanceof Element && child.contains(node)); }
    setAttribute(name,value) { this[name]=value; }
    set src(value) { this.url=value; queueMicrotask(()=>this.onload()); }
  }
  globalThis.document={createElement:tag=>new Element(tag)};
  const root=new Element('div');root.children.push('stale');
  const photo=(id,is_free)=>({id,is_free,visit_date:'2026-01-01',preview_url:`/api/public/results/r/previews/${id}`});
  renderPublicPhotoGallery(root,{venues:[{name:'<script>unsafe</script>',personal:[photo('paid',false),photo('free',true)],common:[photo('common',true)]},{name:'Unmatched',personal:[],common:[photo('arbitrary',true)]}]});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(root.hidden,false);assert.equal(root.children.length,2);
  assert.equal(root.children[0].children[0].textContent,'<script>unsafe</script>');
  const grids=root.children[0].children.filter(node=>node.tag==='div');
  assert.deepEqual(grids.flatMap(g=>g.children.map(n=>n.dataset.photoId)),['paid','free','common']);
  assert.equal(grids[0].children[0].children[0].children[0].url,'/api/public/results/r/previews/paid');
  assert.equal(grids[0].children[0].children[0].children[1].className,'fm-photo-watermark');
  assert.match(grids[0].children[1].children[1].textContent,/Бесплатно/);
  assert.equal(grids[1].children[0].children[0].children.length,1);
  assert.match(grids[1].children[0].children[1].textContent,/Бесплатно/);
  assert.equal(root.children[1].children.length,2);
});

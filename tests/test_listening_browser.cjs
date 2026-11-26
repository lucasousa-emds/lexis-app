const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = __dirname;
const artifacts = process.env.LEXIS_QA_OUTPUT || path.join(require('node:os').tmpdir(), 'lexis-listening-qa');
fs.mkdirSync(artifacts, {recursive:true});
async function run(existingBrowser) {
  const browser = existingBrowser || await require(process.env.LEXIS_PLAYWRIGHT_PATH || 'playwright').chromium.launch({headless:true, executablePath:process.env.LEXIS_BROWSER_PATH || (fs.existsSync('C:/Program Files/Google/Chrome/Application/chrome.exe') ? 'C:/Program Files/Google/Chrome/Application/chrome.exe' : undefined)});
  const context = await browser.newContext();
  let errors = [], requests = [], apiMode = 'success';
  const word = { id:'test_word', word:'test', pos:'noun', definition_en:'a check', definition_pt:'teste', example_1:'This is a test.', subdeck:'02k', status:'pending' };
  await context.addInitScript(() => {
    localStorage.setItem('lexis_listening_v2', JSON.stringify({
      ...JSON.parse(localStorage.getItem('lexis_listening_v2') || '{}'),
      f3ccabbf: {index:0,input:'im honored to be',outcomes:{},assisted:false,unlocked:false,completed:false}
    }));
    window.__ytCalls = [];
    window.YT = { PlayerState: {PLAYING:1}, Player: function(id, config) {
      const iframe = document.createElement('iframe'); iframe.id = id; iframe.title = 'YouTube test double';
      document.getElementById(id).replaceWith(iframe);
      this.time = 0; this.playing = false;
      this.pauseVideo = () => { this.playing = false; window.__ytCalls.push('pause'); config.events.onStateChange({data:2}); };
      this.playVideo = () => { this.playing = true; window.__ytCalls.push('play'); config.events.onStateChange({data:1}); };
      this.seekTo = t => { this.time = t; window.__ytCalls.push(['seek',t]); };
      this.getCurrentTime = () => this.time;
      this.setPlaybackRate = rate => { window.__ytCalls.push(['speed',rate]); };
      this.cueVideoById = id => { this.videoId = id; window.__ytCalls.push(['cue',id]); };
      setTimeout(() => config.events.onReady(), 0);
    }};
  });
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.hostname !== 'lexis.test') return route.abort();
    if (url.pathname === '/') return route.fulfill({contentType:'text/html',body:fs.readFileSync(fs.existsSync(path.join(root,'vocab_review_app.html')) ? path.join(root,'vocab_review_app.html') : path.join(root,'..','vocab_review_app.html'),'utf8')});
    if (url.pathname.startsWith('/static/')) {
      const repoRoot = fs.existsSync(path.join(root, 'static')) ? root : path.join(root, '..');
      const assetPath = path.join(repoRoot, url.pathname.slice(1));
      if (!fs.existsSync(assetPath)) return route.fulfill({status:404, body:'Not Found'});
      const ctype = assetPath.endsWith('.css') ? 'text/css; charset=utf-8' : assetPath.endsWith('.js') ? 'application/javascript; charset=utf-8' : 'application/octet-stream';
      return route.fulfill({contentType: ctype, body: fs.readFileSync(assetPath, 'utf8')});
    }
    if (url.pathname === '/api/evaluate') {
      requests.push(JSON.parse(route.request().postData()));
      if (apiMode === 'network') return route.abort();
      if (apiMode === 'http') return route.fulfill({status:500,json:{error:'test failure'}});
      if (apiMode === 'semantic') return route.fulfill({json:{success:false,error:'not saved'}});
      await new Promise(resolve=>setTimeout(resolve,40));
      return route.fulfill({json:{success:true,stats:{}}});
    }
    if (url.pathname === '/api/status') return route.fulfill({json:{stats:{},active_subdeck:'02k',ready_gaps:0}});
    if (url.pathname === '/api/words') return route.fulfill({json:{words:[word],total:1}});
    if (url.pathname === '/api/gaps') return route.fulfill({json:{gaps:[],ready_count:0,waiting_count:0,injected_count:0}});
    return route.fulfill({json:{success:true}});
  });
  const page = await context.newPage();
  page.on('pageerror',e=>errors.push(e.message));
  const results=[];
  async function test(name, fn) { await fn(); results.push(name); console.log('PASS', name); }
  await page.goto('http://lexis.test/');
  await test('Startup: no JavaScript error, unique IDs, single mobile navigation, no hidden autoplay', async()=>{
    await page.waitForFunction(()=>typeof switchModule === 'function');
    assert.deepEqual(errors,[]);
    assert.equal(await page.locator('.bottom-nav').count(),1);
    assert(await page.evaluate(()=>{const ids=[...document.querySelectorAll('[id]')].map(x=>x.id);return new Set(ids).size===ids.length}));
    assert.equal(await page.evaluate(()=>window.__ytCalls.length),0);
  });
  await page.locator('.topbar [data-module="listening"]').click();
  await page.waitForFunction(()=>ytReady);
  await test('Jobs timing regression: legacy answer restored, 28.2s no longer cuts the sentence, extension retains input', async()=>{
    assert.equal(await page.locator('#dictation-input').inputValue(),'im honored to be');
    assert.equal(await page.evaluate(()=>currentSourceKey),'preset:jobs');
    assert.equal(await page.evaluate(()=>Boolean(listeningSessions.f3ccabbf)),true);
    await page.locator('#dictation-input').press('Alt+r');
    await page.evaluate(()=>{ytPlayer.time=28.2;});
    await page.waitForTimeout(160);
    assert.equal(await page.evaluate(()=>ytPlayer.playing),true);
    assert.equal(await page.evaluate(()=>segmentUnlocked),false);
    await page.evaluate(()=>{ytPlayer.time=30.2;});
    await page.waitForFunction(()=>!ytPlayer.playing);
    await page.getByRole('button',{name:'Ouvir mais 2s',exact:true}).click();
    assert.equal(await page.locator('#dictation-input').inputValue(),'im honored to be');
    assert.equal(await page.evaluate(()=>currentSegmentTiming().end),32.1);
    assert.equal(await page.evaluate(()=>ytPlayer.playing),true);
    assert.equal(await page.evaluate(()=>segmentAssisted),false);
    assert(Math.abs(await page.evaluate(()=>ytPlayer.time)-29.8)<.001);
  });
  await test('Manual timing validation, replay boundaries, persisted per-segment limits and reset preserve the answer',async()=>{
    await page.locator('.dictation-timing-controls summary').click();
    await page.locator('#dictation-start-time').fill('26');
    await page.locator('#dictation-end-time').fill('25');
    await page.getByRole('button',{name:'Aplicar limites',exact:true}).click();
    assert.equal(await page.evaluate(()=>currentSegmentTiming().end),32.1);
    await page.locator('#dictation-end-time').fill('30.5');
    await page.getByRole('button',{name:'Aplicar limites',exact:true}).click();
    await page.locator('#dictation-input').press('Alt+r');
    assert.equal(await page.evaluate(()=>ytPlayer.time),26);
    await page.reload();
    await page.locator('.topbar [data-module="listening"]').click();
    await page.waitForFunction(()=>ytReady);
    assert.equal(await page.locator('#dictation-input').inputValue(),'im honored to be');
    assert.equal(await page.evaluate(()=>currentSegmentTiming().end),30.5);
    await page.evaluate(()=>loadSegment(1,false));
    assert.equal(await page.evaluate(()=>currentSegmentTiming().end),35.2);
    await page.evaluate(()=>loadSegment(0,false));
    assert.equal(await page.evaluate(()=>currentSegmentTiming().end),30.5);
    await page.evaluate(()=>resetDictationTiming());
    assert.equal(await page.evaluate(()=>currentSegmentTiming().end),30.1);
  });
  await test('Contractions preserve were/its and match apostrophes, punctuation and expanded forms', async()=>{
    assert.deepEqual(await page.evaluate(()=>getCleanTargetTokens("We were checking its color.")),['we','were','checking','its','color']);
    assert.deepEqual(await page.evaluate(()=>getCleanTargetTokens("We’re here, and I don't know.")),['we','are','here','and','i','do','not','know']);
    assert.equal(await page.evaluate(()=>expandContractions(normalizeDictationText('I cannot go'))===expandContractions(normalizeDictationText('I can not go'))),true);
    for (const pair of [["He's been here.",'He has been here.'],["I'd finished.",'I had finished.'],["I'd go.",'I would go.']]) {
      assert.equal(await page.evaluate(([left,right])=>{const {user,target}=alignDictationTokens(left,right);return user.join(' ')===target.join(' ')},pair),true);
    }
  });
  const sample = "WEBVTT\n\nNOTE do not parse\n00:00:00.000 --> 00:00:01.000\nignore\n\ncue-1\n00:00:00.100 --> 00:00:00.450 align:start\n<v Alice>You're here.</v>\n\n2\n00:00:00.600 --> 00:00:01.000\nWe were ready.\n\n3\n00:00:01.200 --> 00:00:01.600\nFinal line.\n\n4\n00:00:02.000 --> 00:00:01.000\nInvalid\n";
  await test('SRT/VTT parsing: BOM, cues, tags, comments, invalid timing and numeric speech', async()=>{
    const segs = await page.evaluate(text=>parseSRTorVTT(text),sample);
    assert.equal(segs.length,3); assert.equal(segs[0].en,"You're here."); assert.equal(segs[0].start,.1);
    const numeric = await page.evaluate(()=>parseSRTorVTT('\uFEFF1\r\n00:00:00,000 --> 00:00:01,000\r\n2026\r\n'));
    assert.equal(numeric[0].en,'2026');
  });
  await test('Typing, contraction slots, typo replacement hint and assisted result', async()=>{
    await page.evaluate(()=>{ activeVideoData={videoId:'UF8uR6Z6KLc',title:'test',segments:[{start:0,end:.4,en:"You're here.",pt:''},{start:.6,end:1,en:'We were ready.',pt:''},{start:1.2,end:1.6,en:'Final line.',pt:''}]}; selectedYoutubeData=activeVideoData; activateDictationData(); });
    await page.locator('#dictation-input').fill('you are heer ');
    await page.getByRole('button',{name:/Pista da Palavra/}).click();
    assert.equal(await page.locator('#dictation-input').inputValue(),'you are here ');
    assert.match(await page.locator('#dictation-result-label').textContent(),/ajuda/);
    assert.deepEqual(await page.locator('.word-slot').allTextContents(),['✓ you','✓ are','✓ here']);
    await page.locator('#dictation-input').press('Enter');
    assert.equal(await page.locator('#dictation-input').getAttribute('readonly'),null);
    await page.locator('#dictation-input').fill('We were ready.');
    assert.match(await page.locator('#dictation-result-label').textContent(),/sem pistas/);
  });
  await test('Reveal does not save to Anki or count as independent success; completion does not restart', async()=>{
    const count=requests.length;
    await page.locator('#dictation-next-btn').click();
    await page.getByRole('button',{name:/Revelar Frase/}).click();
    assert.match(await page.locator('#dictation-result-label').textContent(),/revelada/);
    assert.equal(requests.length,count);
    await page.locator('#dictation-next-btn').click();
    assert.match(await page.locator('#dictation-summary').textContent(),/Sem pistas: 1.*Com ajuda: 1.*Reveladas: 1/);
    assert.equal(await page.evaluate(()=>currentSegmentIndex),2);
  });
  await test('Session survives reload with input, outcomes and summary',async()=>{
    const saved=await page.evaluate(()=>JSON.parse(JSON.stringify(activeVideoData)));
    await page.reload(); await page.evaluate(data=>{activeVideoData=data;selectedYoutubeData=data;activateDictationData();switchModule('listening')},saved);
    assert.match(await page.locator('#dictation-summary').textContent(),/Sem pistas: 1/);
    assert.equal(await page.evaluate(()=>currentSegmentIndex),2);
  });
  await test('Confirmed Anki enqueue, duplicate click coalescing and stable IDs',async()=>{
    const before=requests.length;
    await page.evaluate(()=>Promise.all([saveCurrentSegmentToAnki(),saveCurrentSegmentToAnki()]));
    assert.equal(requests.length,before+1);
    assert.equal(requests.at(-1).word,'Final line.');
    await page.evaluate(()=>saveCurrentSegmentToAnki());
    assert.equal(requests.length,before+1);
  });
  await test('HTTP error, semantic error and network failure create real local pending queue; retry confirms',async()=>{
    for (const mode of ['http','semantic','network']) {
      apiMode=mode;
      await page.evaluate(mode=>{activeVideoData={videoId:'UF8uR6Z6KLc',segments:[{start:0,end:.4,en:'Failure '+mode,pt:''}]}; activateDictationData();},mode);
      assert.equal(await page.evaluate(()=>saveCurrentSegmentToAnki()),false);
    }
    assert.equal(await page.evaluate(()=>Object.keys(JSON.parse(localStorage.getItem(LISTENING_STORAGE+'_pending'))).length),3);
    apiMode='success'; await page.evaluate(()=>retryPendingListening());
    assert.equal(await page.evaluate(()=>Object.keys(pendingListening).length),0);
  });
  await test('Custom YouTube URL has no invented transcript; Shorts supported; lookalike domains rejected',async()=>{
    await page.locator('#yt-url-input').fill('https://www.youtube.com/shorts/UF8uR6Z6KLc');
    await page.getByRole('button',{name:'Carregar',exact:true}).click();
    assert.equal(await page.evaluate(()=>activeVideoData.segments.length),0);
    assert.equal(await page.locator('#dictation-input').isDisabled(),true);
    await page.locator('#yt-url-input').fill('https://youtube.com.evil.test/watch?v=11111111111');
    await page.getByRole('button',{name:'Carregar',exact:true}).click();
    assert.equal(await page.evaluate(()=>activeVideoData.videoId),'UF8uR6Z6KLc');
    await page.locator('input[onchange="onYoutubeSrtSelected(event)"]').setInputFiles({name:'captions.vtt',mimeType:'text/vtt',buffer:Buffer.from(sample)});
    await page.waitForFunction(()=>activeVideoData.segments.length===3);
    assert.equal(await page.locator('#dictation-input').isDisabled(),false);
  });
  await test('Tab remains keyboard navigation; Alt+R replays; module switch pauses YouTube',async()=>{
    await page.locator('#dictation-input').focus(); await page.keyboard.press('Tab');
    assert.notEqual(await page.evaluate(()=>document.activeElement.id),'dictation-input');
    await page.locator('#dictation-input').press('Alt+r');
    assert.equal(await page.evaluate(()=>ytPlayer.playing),true);
    await page.evaluate(()=>{ytPlayer.time=.46;});
    await page.waitForFunction(()=>!ytPlayer.playing);
    assert.equal(await page.evaluate(()=>videoTimeCheckInterval),null);
    await page.locator('#dictation-input').press('Alt+r');
    await page.locator('.topbar [data-module="vocab"]').click();
    assert.equal(await page.evaluate(()=>ytPlayer.playing),false);
  });
  const wav=Buffer.alloc(44+16000*2*2); wav.write('RIFF');wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(16000,24);wav.writeUInt32LE(32000,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(wav.length-44,40);
  await page.locator('.topbar [data-module="listening"]').click();
  await page.locator('#btn-mode-audio').click();
  await test('Real audio: metadata, playback, seek, speed, transcript, segment bounds and submode pause',async()=>{
    await page.locator('#listening-audio-file').setInputFiles({name:'test.wav',mimeType:'audio/wav',buffer:wav});
    await page.waitForFunction(()=>listeningAudio().duration===2);
    assert.equal(await page.locator('#listening-total').textContent(),'00:02');
    await page.locator('#listening-play-btn').click();
    await page.waitForFunction(()=>!listeningAudio().paused);
    await page.locator('#listening-speed-btn').click();
    assert.equal(await page.evaluate(()=>listeningAudio().playbackRate),1.25);
    await page.evaluate(()=>onListeningSeek(1));
    assert((await page.evaluate(()=>listeningAudio().currentTime))>=1);
    await page.locator('input[onchange="onListeningCaptionsSelected(event)"]').setInputFiles({name:'audio.vtt',mimeType:'text/vtt',buffer:Buffer.from(sample)});
    await page.waitForFunction(()=>audioTracks.length===3);
    await page.locator('#btn-reveal-transcript').click();
    assert.equal(await page.locator('#listening-sentence-en').textContent(),"You're here.");
    await page.locator('#listening-play-btn').click();
    await page.waitForFunction(()=>listeningAudio().paused);
    assert((await page.evaluate(()=>listeningAudio().currentTime))<.8);
    await page.getByRole('button',{name:'Próximo trecho',exact:true}).click();
    assert.equal(await page.evaluate(()=>audioTrackIndex),1);
    await page.locator('#listening-play-btn').click();
    await page.locator('#btn-mode-video').click();
    assert.equal(await page.evaluate(()=>listeningAudio().paused),true);
  });
  await test('Local video file and captions use independent source state; real playback pauses at cue end',async()=>{
    const fixture=await page.evaluate(async()=>{
      const canvas=document.createElement('canvas');canvas.width=160;canvas.height=90;
      const ctx=canvas.getContext('2d');const stream=canvas.captureStream(15);const chunks=[];
      const recorder=new MediaRecorder(stream,{mimeType:'video/webm'});
      recorder.ondataavailable=e=>chunks.push(e.data);
      const done=new Promise(resolve=>recorder.onstop=resolve);recorder.start();
      const interval=setInterval(()=>{ctx.fillStyle='navy';ctx.fillRect(0,0,160,90);ctx.fillStyle='white';ctx.fillText(String(Date.now()),4,40);},40);
      await new Promise(resolve=>setTimeout(resolve,1800));recorder.stop();await done;clearInterval(interval);stream.getTracks().forEach(t=>t.stop());
      return Array.from(new Uint8Array(await new Blob(chunks,{type:'video/webm'}).arrayBuffer()));
    });
    await page.locator('#btn-src-local').click();
    await page.locator('#local-video-input').setInputFiles({name:'test.webm',mimeType:'video/webm',buffer:Buffer.from(fixture)});
    await page.waitForFunction(()=>document.getElementById('local-video-player').readyState>=1);
    await page.locator('#local-srt-input').setInputFiles({name:'local.vtt',mimeType:'text/vtt',buffer:Buffer.from(sample)});
    await page.waitForFunction(()=>activeVideoData.segments.length===3);
    await page.locator('#dictation-input').press('Alt+r');
    await page.waitForFunction(()=>document.getElementById('local-video-player').paused);
    assert((await page.evaluate(()=>document.getElementById('local-video-player').currentTime))<=.5);
    await page.locator('#dictation-input').fill('you are here');
    assert.match(await page.locator('#dictation-result-label').textContent(),/sem pistas/);
    await page.locator('#btn-src-yt').click();
    assert.equal(await page.evaluate(()=>activeVideoData.isLocal || false),false);
    assert.equal(await page.evaluate(()=>document.getElementById('local-video-player').paused),true);
  });
  await test('Late subtitle reads cannot replace a newly selected source; blank/invalid captions are rejected',async()=>{
    const count=await page.evaluate(()=>activeVideoData.segments.length);
    await page.evaluate(async()=>{
      let resolve;
      const delayed=new Promise(r=>resolve=r);
      const task=onYoutubeSrtSelected({target:{files:[{text:()=>delayed}]}});
      selectedYoutubeData={videoId:'11111111111',title:'new source',segments:[]};
      activeVideoData=selectedYoutubeData;activateDictationData();
      resolve('1\n00:00:00,000 --> 00:00:00,400\nStale caption.\n');
      await task;
    });
    assert.equal(await page.evaluate(()=>activeVideoData.segments.length),0);
    await page.evaluate(()=>onYoutubeSrtSelected({target:{files:[{text:async()=> 'not a subtitle'}]}}));
    assert.equal(await page.evaluate(()=>activeVideoData.segments.length),0);
    await page.locator('#video-preset-select').selectOption('jobs');
  });
  await test('Progress restores a partially typed answer; imported markup remains text; extras cannot pass',async()=>{
    await page.evaluate(()=>{activeVideoData={videoId:'UF8uR6Z6KLc',segments:[{start:0,end:.4,en:'A safe phrase.',pt:''}]};selectedYoutubeData=activeVideoData;activateDictationData();});
    await page.locator('#dictation-input').fill('a safe phrase extra');
    assert.equal(await page.evaluate(()=>segmentUnlocked),false);
    await page.locator('#dictation-input').fill('a saf');
    const data=await page.evaluate(()=>JSON.parse(JSON.stringify(activeVideoData)));
    await page.reload();
    await page.evaluate(data=>{activeVideoData=data;selectedYoutubeData=data;activateDictationData();switchModule('listening')},data);
    assert.equal(await page.locator('#dictation-input').inputValue(),'a saf');
    await page.evaluate(()=>{activeVideoData={videoId:'UF8uR6Z6KLc',segments:[{start:0,end:.4,en:'<img src=x onerror=alert(1)> hello',pt:''}]};selectedYoutubeData=activeVideoData;activateDictationData();giveUpAndReveal();});
    assert.equal(await page.locator('#dictation-word-slots img').count(),0);
    assert.equal(await page.locator('#dictation-revealed-en img').count(),0);
    await page.locator('#video-preset-select').selectOption('jobs');
  });
  await test('Desktop and mobile layouts: no horizontal overflow, single nav, adequate touch controls',async()=>{
    for (const width of [1440,768,767,390,320]) {
      await page.setViewportSize({width,height:900});
      await page.evaluate(()=>switchModule('listening'));
      await page.evaluate(()=>window.scrollTo(0,0));
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth), 'overflow at '+width);
      const nav=page.locator('.bottom-nav');
      if(width<=768) {assert(await nav.isVisible());const rect=await nav.boundingBox();assert(Math.abs(rect.y+rect.height-900)<2);}
      await page.screenshot({path:path.join(artifacts,'listening-'+width+'.png'),fullPage:true});
    }
  });
  await test('Vocabulary focus/grid/gaps, subdeck changes, shortcuts and undo remain callable',async()=>{
    await page.setViewportSize({width:1440,height:900});
    await page.evaluate(()=>switchModule('vocab'));
    await page.locator('#tab-batch').click(); assert(await page.locator('#view-batch').isVisible());
    await page.locator('#tab-gaps').click(); assert(await page.locator('#view-gaps').isVisible());
    await page.locator('#tab-focus').click();
    await page.selectOption('#select-subdeck','01k');
    await page.waitForFunction(()=>localStorage.getItem('lexi_selected_subdeck')==='01k');
    const calls=await page.evaluate(()=>{
      const calls=[];const oldEval=evaluateCurrent,oldUndo=undoLastEvaluation;
      evaluateCurrent=status=>calls.push(status);undoLastEvaluation=()=>calls.push('undo');
      document.activeElement.blur();
      for(const key of ['1','2','3','z','u'])window.dispatchEvent(new KeyboardEvent('keydown',{key,bubbles:true}));
      switchModule('listening');window.dispatchEvent(new KeyboardEvent('keydown',{key:'1',bubbles:true}));
      evaluateCurrent=oldEval;undoLastEvaluation=oldUndo;return calls;
    });
    assert.deepEqual(calls,['conhecido','desconhecido','duvida','undo','undo']);
  });
  assert.deepEqual(errors,[],'uncaught browser errors');
  fs.writeFileSync(path.join(artifacts,'browser-results.json'),JSON.stringify({passed:results,errors,requests:requests.length,engine:browser.version()},null,2));
  await context.close();if(!existingBrowser)await browser.close();
  return {passed:results.length,errors};
}
module.exports={run};
if(require.main===module)run().then(console.log).catch(e=>{console.error(e);process.exitCode=1;});

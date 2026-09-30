// Isolated review UI only; no project writes or solver execution.
async page=>{
 const checks=[],errors=[];const check=(v,m)=>{if(!v)throw Error(m);checks.push(m);};page.on('pageerror',e=>errors.push(e.message));
 const origin=new URL(page.url()).origin;await page.goto(origin);await page.setViewportSize({width:1440,height:1050});await page.evaluate(()=>CFDI18n.setLanguage('ko'));
 const response=await page.request.post(origin+'/api/executions/form-from-survey',{data:{solver:'icoFoam',answers:{medium:'gas',purpose:'flow',regime:'laminar',time_mode:'transient',domain:'internal',mesh:'import',termination:'physical_time'}}});const generated=(await response.json()).result;
 await page.evaluate(g=>{window.configGuided=g;window.configSaved=[];const config=structuredClone(g.config);config.materials.fluids.fluid.density.value=123;CFDFormConfig.open({config,schema:CFDFormConfig.fromConfig(config,g.config_schema),valuesOnly:true,title:'프로젝트 Config',onSave:(value,schema)=>configSaved.push({value,schema})});},generated);
 let d=page.locator('.fc-dialog');await d.waitFor();
 check(await d.locator('.fc-toolbar').getByRole('button',{name:'공간 JSON',exact:true}).count()===0,'spatial action is absent from global toolbar');
 check(await d.locator('.fc-tools').getByRole('button',{name:'전체 JSON',exact:true}).count()===1,'JSON is on the right');
 check(await d.getByRole('button',{name:'구조 편집',exact:true}).count()===0,'project values cannot edit the Template structure');
 await d.locator('.fc-nav').getByRole('button',{name:'재료 물성',exact:true}).click();
 check(await d.locator('[data-config-path="materials.fluids.fluid.kinematic_viscosity.value"]').count()===1,'required viscosity is editable');
 check(await d.locator('[data-config-path="materials.fluids.fluid.density.value"]').count()===0,'optional density is initially hidden');
 check(await d.locator('input[aria-label$=" JSON 키"]').count()===0,'value entry does not expose key or type editing');
 await d.locator('[data-config-path="materials.fluids.fluid.kinematic_viscosity.value"]').fill('0.000001');
 await d.screenshot({path:'output/playwright/config-guided-values.png'});
 await d.locator('.fc-nav').getByRole('button',{name:'초기 조건',exact:true}).click();
 check(await d.locator('.fc-vector').count()===1,'velocity axes are adjacent');
 await d.locator('[data-config-path="initial_conditions.fields.U.x"]').fill('2');
 await d.locator('.fc-nav').getByRole('button',{name:'경계조건',exact:true}).click();
 check(await d.locator('[data-config-path="boundary_conditions.inlet.fields.U.type"]').count()===1,'boundary type remains visible beside value group');
 check(await d.locator('[data-config-path="boundary_conditions.inlet.fields.U.value.x"]').count()===1,'conditional boundary velocity remains accessible');
 await d.getByRole('checkbox',{name:'전체 항목',exact:true}).check();await d.locator('.fc-nav').getByRole('button',{name:'재료 물성',exact:true}).click();
 check(await d.locator('[data-config-path="materials.fluids.fluid.density.value"]').inputValue()==='123','hidden optional input retains existing value');
 await d.locator('.fc-nav').getByRole('button',{name:'형상',exact:true}).click();await d.locator('.fc-main .fc-titlebar').getByRole('button',{name:'JSON',exact:true}).click();await d.locator('.fc-json-pane').getByRole('button',{name:'취소',exact:true}).click();
 await d.getByRole('button',{name:'저장',exact:true}).click();await d.waitFor({state:'detached'});
 check(await page.evaluate(()=>configSaved[0].value.materials.fluids.fluid.density.value===123&&configSaved[0].value.materials.fluids.fluid.kinematic_viscosity.value===.000001&&configSaved[0].value.initial_conditions.fields.U.x===2),'editing updates only selected values and retains optional data');
 await page.evaluate(()=>CFDFormConfig.open({config:configGuided.config,schema:configGuided.config_schema,schemaOnly:true,title:'Config 양식',onSave:(value,schema)=>configSaved.push({value,schema})}));d=page.locator('.fc-dialog');
 await d.locator('.fc-nav').getByRole('button',{name:'재료 물성',exact:true}).click();
 check(await d.locator('.fc-main input[data-config-path]:not([readonly])').count()===0,'Template overview has no physical value inputs');
 await d.locator('.fc-main').getByRole('button',{name:'항목 추가',exact:true}).click();await d.getByRole('textbox',{name:'표시 이름',exact:true}).fill('추가 실험값');await d.getByRole('textbox',{name:'JSON 키',exact:true}).fill('experiment_value');
 check(await d.getByRole('combobox',{name:'입력할 내용',exact:true}).locator('option').allTextContents().then(x=>x.includes('숫자')&&!x.includes('number')),'add-field formats use familiar Korean labels');
 await d.screenshot({path:'output/playwright/config-guided-field.png'});await d.locator('.fc-add').getByRole('button',{name:'추가',exact:true}).click();
 await d.getByRole('button',{name:'구조 편집',exact:true}).click();check(await d.locator('input[aria-label$=" JSON 키"]').count()>0,'advanced structure editor still permits custom keys');
 await d.getByRole('button',{name:'전체 JSON',exact:true}).click();const schema=JSON.parse(await d.locator('.fc-json').inputValue());const custom=schema.fields.find(x=>x.key==='materials').fields.find(x=>x.key==='experiment_value');check(custom.label==='추가 실험값'&&custom.value===null&&custom.type==='number','custom label and blank numeric type survive JSON export');
 await d.locator('.fc-json-pane').getByRole('button',{name:'취소',exact:true}).click();await page.evaluate(()=>CFDI18n.setLanguage('en'));await d.getByRole('button',{name:'Edit structure',exact:true}).waitFor();check(await d.getByRole('checkbox',{name:'All fields',exact:true}).count()===1,'English controls translate');
 await page.evaluate(()=>CFDI18n.setLanguage('ja'));await d.getByRole('button',{name:'構造を編集',exact:true}).waitFor();check(await d.getByRole('checkbox',{name:'すべての項目',exact:true}).count()===1,'Japanese controls translate');await page.evaluate(()=>CFDI18n.setLanguage('ko'));
 await d.getByRole('button',{name:'저장',exact:true}).click();await d.waitFor({state:'detached'});check(await page.evaluate(()=>configSaved[1].schema.fields.find(f=>f.key==='materials').fields.find(f=>f.key==='experiment_value').label==='추가 실험값'),'display name is retained when applying a Template');
 // Read-only legacy Case: spatial preview belongs to geometry, not the header.
 const forms=await (await page.request.get(origin+'/api/executions/forms')).json();const warehouse=forms.forms.find(f=>f.config?.geometry_spec);check(!!warehouse,'legacy warehouse fixture exists');
 await page.evaluate(c=>CFDSettings.open({config:c,readonly:true,title:'Case Config'}),warehouse.config);const settings=page.locator('.fc-dialog');
 await settings.locator('.fc-preview canvas').waitFor();
 await settings.locator('.fc-nav').getByRole('button',{name:'저장고 형상',exact:true}).click();
 await settings.locator('.fc-main .fc-titlebar').getByRole('button',{name:'JSON',exact:true}).click();
 check(await settings.locator('.fc-json-pane textarea').getAttribute('readonly')!==null,'Case geometry JSON preserves read-only snapshot');
 await settings.screenshot({path:'output/playwright/config-warehouse-geometry.png'});
 await settings.locator('.fc-actions').last().getByRole('button',{name:'닫기',exact:true}).click();
 check(errors.length===0,'no browser runtime errors: '+errors.join('; '));return {count:checks.length,checks};
}

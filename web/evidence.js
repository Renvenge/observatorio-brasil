'use strict';
function findingLabel(f){
 if(f.rule==='campos-coincidentes-v1')return 'Possível duplicidade de cadastro';
 if(f.rule==='variacao-valor-v1')return 'Valor global acima do inicial';
 return f.suggested_name||f.title||'Padrão para conferir';
}
function renderFinding(f,r){
 const e=f.evidence||{},percent=v=>Number.isFinite(v)?v.toLocaleString('pt-BR',{maximumFractionDigits:2})+'%':'Não informado';
 let body='',check='',limit='Este sinal não comprova corrupção nem permite calcular prejuízo.';
 if(f.rule==='campos-coincidentes-v1'){
  const ids=[...new Set(e.related_ids||[])];
  body=`<p><strong>${ids.length} registros diferentes têm campos coincidentes.</strong> Confira se representam contratações distintas ou repetição de cadastro.</p><h4>O que coincide na consulta que gerou o sinal</h4><p>${(e.matching_fields||[]).map(esc).join(' · ')}</p><h4>Compare os contratos</h4><div class="comparison-grid">${ids.map((id,i)=>{
   const c=data.contracts.find(x=>x.id===id);
   return `<section class="comparison-card"><h4>Contrato ${i+1}${id===r.id?' · aberto agora':''}</h4><p class="small">${esc(id)}</p>${c?`<dl><dt>Órgão</dt><dd>${esc(c.organization)}</dd><dt>Fornecedor</dt><dd>${esc(c.supplier)}</dd><dt>Objeto</dt><dd>${esc(c.object)}</dd><dt>Valor contratado</dt><dd><strong>${money(c.value)}</strong></dd><dt>Vigência</dt><dd>${esc(c.start)} a ${esc(c.end)}</dd></dl><p>${link(c.source,'Consultar este contrato')}</p>`:'<p>Registro relacionado indisponível nesta publicação. Consulte a fonte da coleta abaixo.</p>'}</section>`;
  }).join('')}</div><p class="small">Os cartões mostram a última versão publicada. Data de assinatura e identificador da compra, usados no critério, devem ser conferidos na fonte oficial; vigência não é data de assinatura.</p>`;
  check='Conferir os números dos contratos, lotes, documentos de assinatura e justificativas. Para verificar pagamento em dobro, é necessário localizar os pagamentos e sua vinculação a cada contrato.';
  limit='Campos iguais podem resultar de contratos separados legítimos, lotes ou cadastro repetido. Não há comprovação de pagamento em dobro; os valores não representam prejuízo apurado.';
 }else if(f.rule==='variacao-valor-v1'){
  const initial=e.valorInicial,total=e.valorGlobal;
  body=`<p>O valor global informado na fonte está <strong>${percent(e.percentual)} acima do valor inicial</strong>.</p><div class="facts">${fact('Valor inicial',money(initial))}${fact('Valor global',money(total))}${fact('Diferença entre os campos',typeof total==='number'&&typeof initial==='number'?money(total-initial):'Não informada')}${fact('Variação',percent(e.percentual))}</div>`;
  check='Consultar aditivos, reajustes, quantidades e mudanças de escopo. Conferir as justificativas e os preços de itens equivalentes antes de concluir que houve sobrepreço.';
  limit='O filtro de 25% é exploratório, não um limite legal. Diferença de valor contratado não é pagamento, prejuízo ou superfaturamento comprovado.';
 }else if(f.comparison?.group_medians){
  const m=f.comparison.group_medians, numeric=v=>typeof v==='number'&&Number.isFinite(v),inv=v=>numeric(v)?Math.expm1(v):null;
  const start=Date.parse(e.dataVigenciaInicio),end=Date.parse(e.dataVigenciaFim),days=Number.isFinite(start)&&Number.isFinite(end)?(end-start)/86400000:null;
  const variation=numeric(e.valorInicial)&&e.valorInicial>0&&numeric(e.valorGlobal)?100*(e.valorGlobal/e.valorInicial-1):null;
  const rows=[['Valor global',money(e.valorGlobal),money(inv(m[0]))],['Variação sobre o inicial',percent(variation),percent(numeric(m[1])?m[1]*100:null)],['Duração contratual',days===null?'Não informada':nf.format(Math.round(days))+' dias',inv(m[2])===null?'Não informada':nf.format(Math.round(inv(m[2])))+' dias']];
  body=`<p>${esc(f.suggested_name||f.title)}</p><p>A IA comparou este contrato com um grupo de <strong>${esc(f.group?.size??'quantidade não informada')} contratos</strong>, separado por UF, esfera, categoria e tipo.</p><div class="table-wrap"><table><thead><tr><th>Informação</th><th>Este contrato</th><th>Referência central do grupo*</th></tr></thead><tbody>${rows.map(row=>'<tr>'+row.map(v=>'<td>'+esc(v)+'</td>').join('')+'</tr>').join('')}</tbody></table></div><p class="small">*Mediana usada pelo modelo, reconvertida para reais, porcentagem e dias; valores aproximados. Não é preço de mercado. O grupo pode reunir objetos e quantidades diferentes.</p>`;
  check=(f.next_steps||['Conferir documentos e condições equivalentes']).join('. ')+'.';
  limit='Uma combinação incomum pode ter explicação legítima. O resultado da IA não é probabilidade de corrupção nem comparação de preços unitários.';
 }else{
  body=`<p>${esc(f.explanation||f.classification||f.status||'Critério sem explicação disponível nesta publicação.')}</p>`;
  check='Conferir o registro oficial e os documentos antes de interpretar este sinal.';
 }
 return `<article class="evidence"><div class="eyebrow">SINAL AUTOMÁTICO · EXIGE CONFERÊNCIA</div><h3>${esc(findingLabel(f))}</h3><h4>O que chamou atenção</h4>${body}<h4>O que falta verificar</h4><p>${esc(check)}</p><div class="notice">${esc(limit)}</div>${f.alternatives?.length?'<p>Possíveis explicações: '+f.alternatives.map(esc).join('; ')+'.</p>':''}<p>${link(r.source,'Abrir contrato oficial')} · ${link(f.source,'Fonte da coleta')}</p><details><summary>Dados técnicos do alerta (opcional)</summary><p class="small">Registro para auditoria e reprodução do critério.</p>${pretty(f)}</details></article>`;
}

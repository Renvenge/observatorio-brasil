'use strict';
const electoralStatus=v=>!v||String(v).startsWith('#')?'Não informado na fonte':v;
function renderAssociations(){
 const coverage=data.meta.political_links, entries=data.associations||[];
 $('section-title').textContent='Políticos e fornecedores';
 $('section-subtitle').textContent=coverage?`Nome e CPF parcial coincidentes · Receita: ${coverage.reference_month||'ainda não consultada'} · ${coverage.parts.length}/${coverage.expected_parts} arquivos consultados. Não confirma identidade ou corrupção.`:'Cruzamento ainda não publicado. Ausência de resultados não significa ausência de vínculos.';
 $('only-alerts').parentElement.hidden=true;$('sort').disabled=true;
 const query=norm($('search').value),uf=$('uf').value;
 filtered=entries.filter(r=>(!uf||r.uf===uf)&&(!query||norm([r.contract_id,r.candidate.name,r.candidate.ballot_name,r.candidate.party,r.candidate.uf,r.supplier,r.supplier_cnpj,r.organization,r.city].join(' ')).includes(query)));
 const pages=Math.max(1,Math.ceil(filtered.length/25));page=Math.min(page,pages);
 $('results').textContent=nf.format(filtered.length)+' correspondências a conferir · estado do contrato';
 $('page').textContent=`Página ${page} de ${pages}`;$('prev').disabled=page===1;$('next').disabled=page===pages;$('export').disabled=!filtered.length;
 $('table-head').innerHTML='<tr><th>Candidatura na fonte eleitoral</th><th>Fornecedor / contratante</th><th>UF do contrato</th><th>Classificação</th></tr>';
 $('rows').innerHTML=filtered.slice((page-1)*25,page*25).map((r,i)=>`<tr><td><button class="open" data-association="${i}"><strong>${esc(r.candidate.name)}</strong></button><small>${esc(r.candidate.office)} · ${esc(r.candidate.year)} · ${esc(r.candidate.party)} / ${esc(r.candidate.uf)}</small><small>${esc(electoralStatus(r.candidate.election_status))} naquela eleição; mandato atual não verificado.</small></td><td>${esc(r.supplier)}<small>${esc(r.organization)}</small><small>${esc(r.contract_id)}</small></td><td>${esc(r.uf)}</td><td><span class="badge neutral">Correspondência a conferir</span><small>Não é sinal financeiro</small></td></tr>`).join('')||'<tr><td colspan="4" class="empty">Nenhuma correspondência nesta seleção. A cobertura é parcial; CPF ausente e nomes diferentes não geram ligação automática.</td></tr>';
 $('rows').querySelectorAll('[data-association]').forEach(b=>b.onclick=()=>openAssociation(filtered[(page-1)*25+Number(b.dataset.association)]));
}

function openAssociation(r){
 const c=r.candidate,contract=data.contracts.find(x=>x.id===r.contract_id);
 const entry=/^\d{8}$/.test(r.entry_date)&&!r.entry_date.startsWith('0000')?`${r.entry_date.slice(6,8)}/${r.entry_date.slice(4,6)}/${r.entry_date.slice(0,4)}`:'Não informada';
 show(`<div class="eyebrow">CORRESPONDÊNCIA A CONFERIR</div><h2>${esc(c.name)}</h2><p>${esc(r.evidence)}</p><div class="notice">${esc(r.limitation)} A relação societária, por si só, não é um sinal de irregularidade.</div>
 <h3>1. Candidatura registrada no TSE</h3><div class="facts">${fact('Eleição',c.election||c.year)}${fact('Cargo disputado',c.office)}${fact('Partido naquela eleição',c.party)}${fact('UF eleitoral',c.uf)}${fact('Resultado naquela eleição',electoralStatus(c.election_status))}${fact('CPF parcial para comparação',c.cpf_mask)}</div><p class="small">Não verificamos o exercício atual do mandato. Partidos e situações podem ter mudado desde a eleição.</p><p>${link(r.candidate_source,'Arquivo oficial do TSE')}</p>
 <h3>2. Nome correspondente no quadro societário</h3><div class="facts">${fact('Pessoa no QSA (sócio ou administrador)',r.partner_name)}${fact('CPF parcial informado',r.cpf_mask)}${fact('Raiz do CNPJ',r.company_base)}${fact('Código da qualificação na Receita',r.qualification_code)}${fact('Data de entrada informada',entry)}${fact('Mês da base societária',r.reference_month)}</div><p>${link(r.source,'Base oficial da Receita Federal')} · arquivo ${esc(r.source_file)}</p><p class="small">Matriz e filiais compartilham a raiz do CNPJ. A correspondência usa nome completo normalizado e seis posições visíveis; pode haver homônimos e colisões.</p>
 <h3>3. Fornecedor de contrato público</h3><div class="facts">${fact('Empresa contratada',r.supplier)}${fact('CNPJ do fornecedor',r.supplier_cnpj)}${fact('Órgão contratante',r.organization)}${fact('Valor contratado — não é pagamento',money(r.contract_value))}${fact('Início do contrato',r.contract_start)}${fact('Localidade',[r.city,r.uf].filter(Boolean).join(' / '))}</div><p>${contract?link(contract.source,'Contrato oficial no PNCP'):esc(r.contract_id)}</p>
 <p class="notice">${r.timing==='entrada_posterior_ao_inicio_do_contrato'?'A entrada no QSA informada é posterior ao início do contrato. Não se pode afirmar que participava da empresa quando o contrato começou.':'O cadastro societário consultado não demonstra a composição da empresa na data do contrato. É necessário conferir documentos históricos.'}</p>
 <h3>Como verificar</h3><p>Confira a identidade em fontes independentes, a composição societária na época do contrato, quem tomou as decisões e as regras aplicáveis. Não inferimos parentesco, favorecimento ou responsabilidade pessoal.</p>
 <details><summary>Datas e identificação das fontes</summary>${pretty({contract_id:r.contract_id,tse_consultado_em:r.candidate_checked_at,tse_sha256:r.candidate_sha256,receita_consultada_em:r.checked_at,receita_sha256:r.sha256,arquivo:r.source_file})}</details>`);
}

function downloadAssociations(){
 const rows=filtered.map(r=>[r.candidate.name,r.candidate.year,r.candidate.party,r.supplier,r.supplier_cnpj,r.contract_id,r.uf,'Correspondência a conferir; identidade não confirmada',r.reference_month,r.candidate_source,r.source]);
 const cell=v=>'"'+String(v??'').replace(/^[\s]*([=+@-])/,"'$1").replaceAll('"','""')+'"';
 const text='\uFEFF'+[['candidatura','ano_eleitoral','partido_na_eleicao','fornecedor','cnpj','contrato','uf_contrato','classificacao','mes_receita','fonte_tse','fonte_receita'],...rows].map(row=>row.map(cell).join(';')).join('\r\n');
 const url=URL.createObjectURL(new Blob([text],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='observatorio-correspondencias-a-conferir.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}

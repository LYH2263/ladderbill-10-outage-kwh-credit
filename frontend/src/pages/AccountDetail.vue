<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { errorMessage, fmtTime, getJSON, postJSON } from '../api'
import SegmentTable from '../components/SegmentTable.vue'

const route = useRoute()
const data = ref(null)
const period = ref('')
const summary = ref(null)
const bill = ref(null)
const peak = ref(false)
const form = ref({ kwh: '', note: '' })
const formError = ref('')
const busy = ref(false)

const account = computed(() => data.value?.account)
const periods = computed(() => {
  const ps = (data.value?.readings || []).map(r => r.period).filter(Boolean)
  return [...new Set(ps)].sort().reverse()
})

async function loadAccount() {
  data.value = await getJSON(`/api/accounts/${route.params.id}`)
  const ps = periods.value
  if (ps.length && !ps.includes(period.value)) period.value = ps[0]
  else if (!ps.length) period.value = ''
}

async function loadSummary() {
  if (!period.value) { summary.value = null; return }
  summary.value = await getJSON(`/api/accounts/${route.params.id}/credits?period=${period.value}`)
  const reading = (data.value?.readings || []).find(r => r.period === period.value)
  peak.value = !!reading?.peak
}

async function previewBill() {
  if (!period.value) { bill.value = null; return }
  bill.value = await postJSON('/api/bill', {
    account_id: +route.params.id,
    period: period.value,
    peak: peak.value,
    persist: false,
  })
}

async function refresh() {
  await loadSummary()
  await previewBill()
}

async function registerCredit() {
  formError.value = ''
  const kwh = Number(form.value.kwh)
  if (!kwh || kwh <= 0) { formError.value = '请输入大于 0 的信用电量'; return }
  busy.value = true
  try {
    await postJSON(`/api/accounts/${route.params.id}/credits`, {
      period: period.value,
      kwh,
      note: form.value.note || null,
    })
    form.value = { kwh: '', note: '' }
    await refresh()
  } catch (e) {
    formError.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}

async function voidCredit(c) {
  const note = window.prompt(`作废 #${c.id}（${c.kwh} kWh），作废原因（可选，记录仍保留可查）：`, c.note || '')
  if (note === null) return
  try {
    await postJSON(`/api/credits/${c.id}/void`, { note: note || null })
    await refresh()
  } catch (e) {
    window.alert(errorMessage(e))
  }
}

onMounted(async () => {
  await loadAccount()
  await refresh()
})
watch(() => route.params.id, async () => { await loadAccount(); await refresh() })
watch(peak, previewBill)
</script>
<template>
  <div class="page" v-if="account">
    <h1>{{ account.name }}</h1>
    <p class="muted">表号 {{ account.meter_no }} · {{ account.note }}</p>

    <div class="panel" v-if="periods.length">
      <label class="period-pick">
        账期
        <select v-model="period" @change="refresh">
          <option v-for="p in periods" :key="p" :value="p">{{ p }}</option>
        </select>
      </label>
      <div class="stat-row" v-if="summary">
        <span>毛电量 <strong>{{ summary.gross_kwh }}</strong></span>
        <span>有效信用合计 <strong class="credit-num">−{{ summary.credit_kwh }}</strong></span>
        <span>净电量 <strong class="hero-num" style="font-size:1.4rem">{{ summary.net_kwh }}</strong></span>
      </div>
    </div>
    <div class="panel" v-else>
      <p class="muted">该户暂无抄表记录，请先录入抄表后再登记停电信用。</p>
    </div>

    <template v-if="period">
      <div class="panel">
        <h3>停电信用明细</h3>
        <table>
          <thead>
            <tr><th>#</th><th>信用电量(kWh)</th><th>事由</th><th>登记时间</th><th>状态</th><th>作废信息</th><th></th></tr>
          </thead>
          <tbody>
            <tr v-for="c in summary?.items || []" :key="c.id" :class="{ voidrow: c.status === 'void' }">
              <td>{{ c.id }}</td>
              <td>{{ c.kwh }}</td>
              <td class="muted">{{ c.note || '—' }}</td>
              <td class="muted">{{ fmtTime(c.created_at) }}</td>
              <td>
                <span :class="c.status === 'void' ? 'tag tag-void' : 'tag tag-active'">
                  {{ c.status === 'void' ? '已作废' : '有效' }}
                </span>
              </td>
              <td class="muted">
                <template v-if="c.status === 'void'">{{ fmtTime(c.voided_at) }}<template v-if="c.void_note"> · {{ c.void_note }}</template></template>
                <template v-else>—</template>
              </td>
              <td>
                <button v-if="c.status === 'active'" class="btn-ghost" @click="voidCredit(c)">作废</button>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="!(summary?.items || []).length" class="muted">本账期暂无信用记录。</p>

        <h3>登记停电信用</h3>
        <div class="form-row">
          <label>信用电量(kWh)
            <input type="number" v-model="form.kwh" min="0" step="0.01" placeholder="如 15" @keyup.enter="registerCredit" />
          </label>
          <label>事由
            <input type="text" v-model="form.note" placeholder="如 台区检修停电" @keyup.enter="registerCredit" />
          </label>
          <button :disabled="busy" @click="registerCredit">登记</button>
        </div>
        <p v-if="formError" class="error">⛔ {{ formError }}</p>
        <p class="muted hint">单笔与有效信用合计均不得超过该账期毛电量（{{ summary?.gross_kwh }} kWh），超额将被拒绝。</p>
      </div>

      <div class="panel">
        <h3>本账期试算（毛电量 − 有效信用 = 净电量）</h3>
        <label><input type="checkbox" v-model="peak" /> 尖峰</label>
        <p v-if="bill">
          毛电量 {{ bill.gross_kwh }} − 信用扣除
          <strong class="credit-num">{{ bill.credit_kwh }}</strong>
          = 净电量 <strong>{{ bill.net_kwh }}</strong> kWh
          ，合计 <strong class="hero-num" style="font-size:1.5rem">¥{{ bill.total }}</strong>
        </p>
        <SegmentTable :rows="bill?.segments || []" />
      </div>
    </template>
  </div>
</template>
<style scoped>
.period-pick select { margin-left: 0.5rem; }
.stat-row { display: flex; gap: 2rem; margin-top: 0.8rem; flex-wrap: wrap; }
.stat-row strong { font-size: 1.15rem; }
.credit-num { color: #e8b34b; }
.form-row { display: flex; flex-wrap: wrap; gap: 1rem; align-items: end; margin-top: 0.5rem; }
input[type=number] { width: 7rem; }
input[type=text] { width: 14rem; }
.hint { margin-top: 0.5rem; font-size: 0.85rem; }
.error { color: #ff8a80; margin-top: 0.6rem; }
.tag { padding: 0.1rem 0.5rem; border-radius: 999px; font-size: 0.78rem; }
.tag-active { background: color-mix(in srgb, var(--accent) 22%, transparent); color: var(--accent); }
.tag-void { background: color-mix(in srgb, #e8b34b 20%, transparent); color: #e8b34b; }
.voidrow td { opacity: 0.62; }
.btn-ghost {
  background: transparent; border: 1px solid var(--muted); color: var(--text);
  padding: 0.2rem 0.6rem; font-size: 0.8rem;
}
</style>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getJSON, postJSON } from '../api'
import SegmentTable from '../components/SegmentTable.vue'

const route = useRoute()
const data = ref(null)
const credits = ref([])
const bill = ref(null)
const peak = ref(false)
const period = ref('2026-09')

// 信用登记表单
const form = ref({ kwh: null, reason: '' })
const formError = ref('')
const busy = ref(false)

const account = computed(() => data.value?.account)
const grossKwh = computed(() => data.value?.readings[0]?.kwh ?? null)
const activeTotal = computed(() =>
  credits.value.filter((c) => c.active).reduce((s, c) => s + c.kwh, 0)
)

async function loadCredits() {
  const r = await getJSON(`/api/accounts/${route.params.id}/credits?period=${period.value}`)
  credits.value = r.items
}

async function trial() {
  if (grossKwh.value == null) return
  bill.value = await postJSON('/api/bill', {
    account_id: +route.params.id,
    period: period.value,
    kwh: grossKwh.value,
    peak: peak.value,
    persist: false,
  })
}

async function refreshAll() {
  data.value = await getJSON(`/api/accounts/${route.params.id}`)
  await loadCredits()
  await trial()
}

async function registerCredit() {
  formError.value = ''
  busy.value = true
  try {
    await postJSON(`/api/accounts/${route.params.id}/credits`, {
      account_id: +route.params.id,
      period: period.value,
      kwh: form.value.kwh,
      reason: form.value.reason || null,
    })
    form.value = { kwh: null, reason: '' }
    await refreshAll()
  } catch (e) {
    formError.value = e.message
  } finally {
    busy.value = false
  }
}

async function voidCredit(c) {
  if (!window.confirm(`确认作废信用 ${c.kwh} kWh？作废后不再参与扣除。`)) return
  await postJSON(`/api/credits/${c.id}/void`, { reason: '户详情手工作废' })
  await refreshAll()
}

onMounted(refreshAll)
watch(() => route.params.id, refreshAll)
watch(period, async () => {
  await loadCredits()
  await trial()
})
watch(peak, trial)
</script>
<template>
  <div class="page" v-if="account">
    <h1>{{ account.name }}</h1>
    <p class="muted">表号 {{ account.meter_no }} · {{ account.note }}</p>

    <div class="panel">
      <h3>停电电量信用</h3>
      <div class="form-row">
        <label>账期 <input type="month" v-model="period" /></label>
        <label>毛电量 <strong>{{ grossKwh ?? '—' }}</strong> kWh</label>
        <label>有效信用合计 <strong>{{ activeTotal }}</strong> kWh</label>
      </div>
      <div class="form-row">
        <label>本笔电量(kWh) <input type="number" v-model.number="form.kwh" min="0" step="1" /></label>
        <label>事由 <input type="text" v-model="form.reason" placeholder="如：线路检修" /></label>
        <button :disabled="busy" @click="registerCredit">登记信用</button>
      </div>
      <p v-if="formError" class="err">⚠ {{ formError }}</p>
      <table>
        <thead>
          <tr><th>账期</th><th>电量</th><th>事由</th><th>状态</th><th>作废说明</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-for="c in credits" :key="c.id" :class="{ voided: !c.active }">
            <td>{{ c.period }}</td>
            <td>{{ c.kwh }}</td>
            <td class="muted">{{ c.reason || '—' }}</td>
            <td>
              <span v-if="c.active" class="tag tag-active">有效</span>
              <span v-else class="tag tag-void">已作废</span>
            </td>
            <td class="muted">{{ c.void_reason || '—' }}</td>
            <td>
              <button v-if="c.active" class="btn-ghost" @click="voidCredit(c)">作废</button>
              <span v-else class="muted">审计行 #{{ c.id }}</span>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="!credits.length" class="muted">该账期暂无信用记录</p>
    </div>

    <div class="panel">
      <h3>账期试算（毛电量 {{ grossKwh }} → 净电量 {{ bill?.net_kwh ?? '—' }}）</h3>
      <label><input type="checkbox" v-model="peak" /> 尖峰</label>
      <button class="btn-ghost" @click="trial">重新试算</button>
      <div v-if="bill" class="credit-strip">
        <span>毛电量 <strong>{{ bill.gross_kwh }}</strong></span>
        <span>信用扣除 <strong class="deduct">−{{ bill.credit.deducted }}</strong></span>
        <span>净电量 <strong class="net">{{ bill.net_kwh }}</strong></span>
        <span>合计 <strong>¥{{ bill.total }}</strong></span>
      </div>
      <SegmentTable :rows="bill?.segments || []" />
    </div>
  </div>
</template>
<style scoped>
.form-row { display: flex; flex-wrap: wrap; gap: 1rem; align-items: end; margin-bottom: 0.75rem; }
.err { color: #ff9d9d; }
.voided { opacity: 0.55; }
.tag { padding: 0.1rem 0.45rem; border-radius: 999px; font-size: 0.8rem; }
.tag-active { background: color-mix(in srgb, var(--accent) 22%, transparent); color: var(--accent); }
.tag-void { background: color-mix(in srgb, #e08a3d 22%, transparent); color: #e0b48a; }
.credit-strip { display: flex; flex-wrap: wrap; gap: 1.5rem; margin: 0.75rem 0; font-size: 1.05rem; }
.deduct { color: #ffb27a; }
.net { color: var(--accent); }
.btn-ghost { background: transparent; border: 1px solid var(--muted); color: var(--text); font-weight: 400; }
</style>

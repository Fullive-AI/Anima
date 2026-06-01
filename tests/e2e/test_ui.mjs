/**
 * Anima UI E2E Test
 * Tests: room management, chat UX, virtual devices
 */
import { chromium } from 'playwright';
import { mkdir } from 'fs/promises';
import { existsSync } from 'fs';

const BASE = 'http://localhost:3000';
const SCREENSHOTS = 'tests/e2e/screenshots';

async function ensureDir(dir) {
  if (!existsSync(dir)) await mkdir(dir, { recursive: true });
}

async function screenshot(page, name) {
  await ensureDir(SCREENSHOTS);
  const path = `${SCREENSHOTS}/${name}.png`;
  await page.screenshot({ path, fullPage: false });
  console.log(`  📸 ${path}`);
}

async function pass(msg) { console.log(`  ✅ ${msg}`); }
async function fail(msg) { console.log(`  ❌ ${msg}`); }

async function runTests() {
  await ensureDir(SCREENSHOTS);
  const browser = await chromium.launch({ headless: false, slowMo: 300 });
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1440, height: 900 });

  let passed = 0;
  let failed = 0;

  try {
    // ── 1. Page loads ──
    console.log('\n[1] 页面加载');
    await page.goto(BASE, { waitUntil: 'networkidle' });
    await screenshot(page, '01-initial-load');
    const title = await page.title();
    if (title) { pass(`页面标题: ${title}`); passed++; }
    else { fail('页面无标题'); failed++; }

    // ── 2. Left sidebar exists ──
    console.log('\n[2] 左侧设备栏');
    const sidebar = await page.locator('aside').first();
    if (await sidebar.isVisible()) { pass('左侧栏可见'); passed++; }
    else { fail('左侧栏不可见'); failed++; }

    // ── 3. Create a room ──
    console.log('\n[3] 创建房间');
    const addRoomBtn = page.locator('button[title="新增房间"]');
    if (await addRoomBtn.isVisible()) {
      await addRoomBtn.click();
      await page.waitForTimeout(300);
      const input = page.locator('input[placeholder="房间名称..."]');
      if (await input.isVisible()) {
        await input.fill('客厅');
        await input.press('Enter');
        await page.waitForTimeout(500);
        await screenshot(page, '02-room-created');
        const roomLabel = page.locator('text=客厅');
        if (await roomLabel.isVisible()) { pass('房间"客厅"创建成功'); passed++; }
        else { fail('房间创建后未显示'); failed++; }
      } else { fail('房间名称输入框未出现'); failed++; }
    } else { fail('新增房间按钮不可见'); failed++; }

    // ── 4. Create second room ──
    console.log('\n[4] 创建第二个房间');
    const addRoomBtn2 = page.locator('button[title="新增房间"]');
    if (await addRoomBtn2.isVisible()) {
      await addRoomBtn2.click();
      await page.waitForTimeout(300);
      const input2 = page.locator('input[placeholder="房间名称..."]');
      if (await input2.isVisible()) {
        await input2.fill('卧室');
        await input2.press('Enter');
        await page.waitForTimeout(500);
        const roomLabel2 = page.locator('text=卧室');
        if (await roomLabel2.isVisible()) { pass('房间"卧室"创建成功'); passed++; }
        else { fail('第二个房间创建后未显示'); failed++; }
      }
    }

    // ── 5. Create virtual device via settings ──
    console.log('\n[5] 创建虚拟设备');
    const settingsBtn = page.locator('button').filter({ hasText: /设置|Settings/ }).first();
    // Try header settings button
    const headerBtns = page.locator('header button, [class*="Header"] button');
    const count = await headerBtns.count();
    let settingsOpened = false;
    for (let i = 0; i < count; i++) {
      const btn = headerBtns.nth(i);
      const label = await btn.getAttribute('aria-label') || await btn.textContent() || '';
      if (label.includes('设置') || label.includes('Settings')) {
        await btn.click();
        settingsOpened = true;
        break;
      }
    }
    if (!settingsOpened) {
      // Try clicking any settings-like button
      const gearBtn = page.locator('button').filter({ has: page.locator('svg') }).nth(2);
      await gearBtn.click();
      settingsOpened = true;
    }

    await page.waitForTimeout(500);
    await screenshot(page, '03-settings-open');

    const virtualSection = page.locator('text=虚拟设备');
    if (await virtualSection.isVisible()) {
      pass('虚拟设备设置区块可见'); passed++;
      const nameInput = page.locator('input[placeholder*="客厅灯"]');
      if (await nameInput.isVisible()) {
        await nameInput.fill('测试虚拟灯');
        const createBtn = page.locator('button').filter({ hasText: '创建虚拟设备' });
        if (await createBtn.isVisible()) {
          await createBtn.click();
          await page.waitForTimeout(1000);
          await screenshot(page, '04-virtual-device-created');
          const successMsg = page.locator('text=已创建');
          if (await successMsg.isVisible()) { pass('虚拟设备创建成功'); passed++; }
          else { fail('虚拟设备创建成功消息未出现'); failed++; }
        } else { fail('创建虚拟设备按钮不可见'); failed++; }
      } else { fail('虚拟设备名称输入框不可见'); failed++; }
    } else { fail('虚拟设备设置区块不可见'); failed++; }

    // Close settings
    const closeBtn = page.locator('button').filter({ has: page.locator('svg[class*="X"], svg[data-lucide="x"]') }).first();
    if (await closeBtn.isVisible()) await closeBtn.click();
    await page.waitForTimeout(500);

    // ── 6. Virtual device badge visible in sidebar ──
    console.log('\n[6] 虚拟设备标签');
    await page.waitForTimeout(1000);
    await screenshot(page, '05-sidebar-with-virtual');
    const virtualBadge = page.locator('text=虚拟').first();
    if (await virtualBadge.isVisible()) { pass('虚拟设备标签显示正常'); passed++; }
    else { fail('虚拟设备标签未显示'); failed++; }

    // ── 7. Chat panel visible ──
    console.log('\n[7] 对话面板');
    const chatPanel = page.locator('aside').last();
    if (await chatPanel.isVisible()) { pass('对话面板可见'); passed++; }
    else { fail('对话面板不可见'); failed++; }

    const chatInput = page.locator('textarea[placeholder*="说点什么"]');
    if (await chatInput.isVisible()) { pass('对话输入框可见'); passed++; }
    else { fail('对话输入框不可见'); failed++; }

    // ── 8. Send a chat message ──
    console.log('\n[8] 发送对话消息');
    if (await chatInput.isVisible()) {
      await chatInput.fill('你好，现在有哪些设备？');
      await chatInput.press('Enter');
      await page.waitForTimeout(3000);
      await screenshot(page, '06-chat-message-sent');
      // Check user bubble appeared
      const userBubble = page.locator('text=你好，现在有哪些设备？');
      if (await userBubble.isVisible()) { pass('用户消息气泡显示'); passed++; }
      else { fail('用户消息气泡未显示'); failed++; }
    }

    // ── 9. No internal decision cards visible ──
    console.log('\n[9] 内部决策卡片已隐藏');
    const planCard = page.locator('text=计划任务:');
    const taskResultCard = page.locator('text=刷新环境状态');
    const planVisible = await planCard.isVisible().catch(() => false);
    const taskVisible = await taskResultCard.isVisible().catch(() => false);
    if (!planVisible && !taskVisible) { pass('内部决策卡片已隐藏'); passed++; }
    else { fail('内部决策卡片仍然可见'); failed++; }

    // ── 10. Final screenshot ──
    await screenshot(page, '07-final-state');

  } catch (err) {
    console.error('\n测试异常:', err.message);
    await screenshot(page, 'error-state').catch(() => {});
    failed++;
  } finally {
    await browser.close();
  }

  console.log(`\n${'─'.repeat(40)}`);
  console.log(`测试结果: ${passed} 通过 / ${failed} 失败`);
  console.log(`截图保存在: ${SCREENSHOTS}/`);
  if (failed > 0) process.exit(1);
}

runTests().catch(err => {
  console.error('Fatal:', err);
  process.exit(1);
});

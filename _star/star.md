---
title: "GitHub 收藏"
permalink: /star/
layout: single
classes: wide
---

<div class="star-grid">

  <!-- 卡片 1 -->
  <div class="star-card">
    <a href="https://github.com/Taylor7992/xxxx" target="_blank">
      <h3>项目名称示例</h3>
      <p>这是项目的简短描述，可自由填写。</p>
    </a>
  </div>

  <!-- 卡片 2 -->
  <div class="star-card">
    <a href="https://github.com/xxxx/xxxx" target="_blank">
      <h3>另一个项目</h3>
      <p>喜欢的开源项目简介。</p>
    </a>
  </div>

</div>

<style>
  .star-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 16px;
  }
  .star-card {
    background: #ffffff;
    padding: 16px;
    border-radius: 10px;
    border: 1px solid #e5e5e5;
    transition: 0.2s;
  }
  .star-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  }
</style>


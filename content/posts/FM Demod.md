---
title: "FM Demodulation in C++"
date: 2020-09-15T11:30:03+00:00
tags: ["RF", "C++", "Programming", "SDR"]
author: "Ben Kyd"
showToc: true
TocOpen: false
draft: false
hidemeta: false
comments: false
description: "Exploring the basics of DSP"
canonicalURL: "https://benkyd.co.uk/posts/fm-demod"
disableHLJS: true # to disable highlightjs
disableShare: false
disableHLJS: false
hideSummary: false
searchHidden: true
ShowReadingTime: true
ShowBreadCrumbs: true
ShowPostNavLinks: true
ShowWordCount: true
ShowRssButtonInSectionTermList: true
---

1. Complex I/Q samples as complex numbers:

\(z[n]=I[n]+jQ[n]\)

\(z[n]=I[n]+jQ[n]\)

where \(I[n]I[n]\) and \(Q[n]Q[n]\) are the in-phase and quadrature components at sample \(nn\)

in c this might look like
```cpp
for (int i = 0; i < n_samples; i++)
{
    int8_t i_sample = rtl_buf[2 * i] - 127;
    int8_t q_sample = rtl_buf[2 * i + 1] - 127;
    iq_buf[i] = atan2(q_sample, i_sample);
}
```


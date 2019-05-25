const express = require('express');
const bodyParser = require('body-parser');
const fs = require('fs');''
const base64Img = require('base64-img');

const router = express.Router();

router.get('/', async (req, res) => {
    res.sendFile(__dirname + '/client/index.html');
});

router.post('/', async (req, res) => {
    let img = req.body.img;
    let base64Data;
    base64Data = img.replace(/^data:image\/png;base64,/,"");
    base64Data = img.replace(/^data:image\/pjpeg;base64,/,"");
    base64Data = img.replace(/^data:image\/jpg;base64,/,"");

    base64Data  +=  base64Data.replace('+', ' ');

    let filepath = await base64Img.imgSync(img, './storage' /* path */, '2' /* name */);
    console.log(filepath)
});

module.exports = router;

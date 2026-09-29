const test=require('node:test'),assert=require('node:assert/strict');
const {parseValue,acceptsEdit}=require('../cfd_studio/internal/input_validation.js');
test('numeric inputs reject text, partial values, blanks and non-finite values',()=>{
 for(const value of ['',' ','12px','NaN','Infinity','1e309','1e','0x10','1,2','-'])assert.throws(()=>parseValue(value,'number'));
 for(const [text,expected] of [['1e-3',.001],['-.5',-.5],['+2',2],['2.',2],[' 3 ',3]])assert.equal(parseValue(text,'number'),expected);
});
test('integer inputs reject fractions and unsafe integers',()=>{for(const text of ['1.2','9007199254740992'])assert.throws(()=>parseValue(text,'integer'));assert.equal(parseValue('2e2','integer'),200);});
test('optional placeholders differ from invalid numbers and required values',()=>{assert.equal(parseValue('','number',{nullable:true}),null);assert.throws(()=>parseValue('abc','number',{nullable:true}));assert.throws(()=>parseValue('','number'));});
test('array and object input checks distinguish valid JSON from the required type',()=>{
 assert.deepEqual(parseValue('[1,2]','array'),[1,2]);assert.deepEqual(parseValue('{"x":2}','object'),{x:2});
 for(const text of ['{}','null','"[]"','[1,]'])assert.throws(()=>parseValue(text,'array'));
 for(const text of ['[]','null','1','{bad}'])assert.throws(()=>parseValue(text,'object'));
 assert.throws(()=>parseValue('{"n":1e309}','object'));assert.equal(parseValue(' any text  ','string'),' any text  ');
});

test('editing admits incomplete numeric prefixes but blocks incompatible characters',()=>{
 for(const text of ['', '-', '.', '-.', '1e', '1e-', '1.5e-3'])assert.equal(acceptsEdit(text,'number'),true,text);
 for(const text of ['a','12px','한글','1e309','1.2.3','e','1e--2'])assert.equal(acceptsEdit(text,'number'),false,text);
 for(const text of ['', '-', '12'])assert.equal(acceptsEdit(text,'integer'),true,text);
 for(const text of ['1.5','1e2','9007199254740992','12a'])assert.equal(acceptsEdit(text,'integer'),false,text);
});
